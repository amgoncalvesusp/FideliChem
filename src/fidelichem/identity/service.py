"""Atomic, audited identity confirmation and append-only decision chains."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from fidelichem.domain.chemistry import (
    Alias,
    CanonicalizationResult,
    IdentityActor,
    IdentityClaim,
    IdentityDecision,
    IdentityResolution,
    IdentitySelection,
    SelectionMode,
)
from fidelichem.domain.errors import IdentityResolutionConflictError
from fidelichem.domain.json import canonical_json
from fidelichem.domain.models import ActorKind, AuditEvent, ImportStatus
from fidelichem.identity.models import (
    CatalogAction,
    IdentityIndex,
    ResolutionKind,
    ResolutionReport,
)
from fidelichem.identity.resolver import IdentityResolver
from fidelichem.storage.repositories import (
    DuplicateRecordError,
    RecordNotFoundError,
    StorageWriteError,
)
from fidelichem.storage.session import UnitOfWork

Clock = Callable[[], datetime]
UowFactory = Callable[[], UnitOfWork]
IndexFactory = Callable[[], IdentityIndex]
Failpoint = Callable[[str], None]


class IdentityService:
    """Own all identity writes behind one auditable transaction boundary."""

    def __init__(
        self,
        uow_factory: UowFactory,
        index_factory: IndexFactory,
        clock: Clock,
        failpoint: Failpoint | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._index_factory = index_factory
        self._clock = clock
        self._failpoint = failpoint

    def confirm_claim(
        self,
        result: CanonicalizationResult | None,
        claim: IdentityClaim,
        report: ResolutionReport,
        selection: IdentitySelection,
        actor: IdentityActor,
        *,
        uow: UnitOfWork | None = None,
    ) -> IdentityResolution:
        result, claim, report, selection, actor = self._validate_confirm_inputs(
            result, claim, report, selection, actor
        )
        if claim.import_batch_id is None or claim.source_system is None:
            raise ValueError("persistence prerequisites are required")
        if claim.source_value is None:
            raise ValueError("persistence prerequisites are required")
        if report.kind is ResolutionKind.NEW_COMPOUND:
            self._hit("before_chemistry")
        elif report.kind is ResolutionKind.NEW_STATE:
            self._hit("before_state")
        if uow is not None:
            # ImportManager may own one transaction for the whole bundle.  The
            # caller reserves the SQLite writer before creating the batch; we
            # intentionally do not open a nested UnitOfWork here.
            from fidelichem.storage.identity_index import PersistentIdentityIndex

            reuse_after_race = self._validate_live_report(
                result,
                claim,
                report,
                selection,
                index=PersistentIdentityIndex(uow.session),
                allow_structure_race=True,
            )
            return self._confirm_in_uow(
                uow,
                result,
                claim,
                report,
                selection,
                actor,
                reuse_after_race=reuse_after_race,
            )
        try:
            self._validate_live_report(
                result,
                claim,
                report,
                selection,
                index=self._index_factory(),
            )
            with self._uow_factory() as uow:
                self._reserve_write(uow)
                reuse_after_race = self._validate_live_report(
                    result,
                    claim,
                    report,
                    selection,
                    index=self._index_factory(),
                    allow_structure_race=True,
                )
                return self._confirm_in_uow(
                    uow,
                    result,
                    claim,
                    report,
                    selection,
                    actor,
                    reuse_after_race=reuse_after_race,
                )
        except DuplicateRecordError:
            if (
                report.kind
                not in {
                    ResolutionKind.NEW_COMPOUND,
                    ResolutionKind.NEW_STATE,
                }
                or result is None
            ):
                raise
            with self._uow_factory() as uow:
                self._reserve_write(uow)
                return self._confirm_in_uow(
                    uow,
                    result,
                    claim,
                    report,
                    selection,
                    actor,
                    reuse_after_race=True,
                )

    def reserve_write(self, uow: UnitOfWork) -> None:
        """Reserve the SQLite writer for a caller-owned import transaction."""

        self._reserve_write(uow)

    def reassign(
        self,
        alias_id: str,
        predecessor_id: str,
        selection: IdentitySelection,
        actor: IdentityActor,
    ) -> IdentityResolution:
        actor = self._validate_actor(actor, require_user=True)
        selection = self._validate_selection(selection)
        if selection.mode is not SelectionMode.EXISTING_TARGET:
            raise ValueError("reassignment requires an existing selection")
        return self._append_transition(
            alias_id,
            predecessor_id,
            selection,
            actor,
            decision=IdentityDecision.REASSIGNED,
        )

    def retract(
        self,
        alias_id: str,
        predecessor_id: str,
        actor: IdentityActor,
    ) -> IdentityResolution:
        actor = self._validate_actor(actor, require_user=True)
        return self._append_transition(
            alias_id,
            predecessor_id,
            None,
            actor,
            decision=IdentityDecision.RETRACTED,
        )

    def restore(
        self,
        alias_id: str,
        predecessor_id: str,
        selection: IdentitySelection,
        actor: IdentityActor,
    ) -> IdentityResolution:
        actor = self._validate_actor(actor, require_user=True)
        selection = self._validate_selection(selection)
        if selection.mode is not SelectionMode.EXISTING_TARGET:
            raise ValueError("restoration requires an existing selection")
        return self._append_transition(
            alias_id,
            predecessor_id,
            selection,
            actor,
            decision=IdentityDecision.RESTORED,
        )

    def _validate_confirm_inputs(
        self,
        result: CanonicalizationResult | None,
        claim: IdentityClaim,
        report: ResolutionReport,
        selection: IdentitySelection,
        actor: IdentityActor,
    ) -> tuple[
        CanonicalizationResult | None,
        IdentityClaim,
        ResolutionReport,
        IdentitySelection,
        IdentityActor,
    ]:
        try:
            claim = IdentityClaim.model_validate(claim)
            report = ResolutionReport.model_validate(report)
            selection = IdentitySelection.model_validate(selection)
            actor = IdentityActor.model_validate(actor)
            if result is not None:
                result = CanonicalizationResult.model_validate(result)
        except (ValidationError, TypeError, ValueError):
            raise ValueError("identity confirmation input is invalid") from None
        if (result is None) != (claim.smiles is None):
            raise ValueError("result and claim SMILES must be supplied together")
        if (
            result is not None
            and claim.smiles is not None
            and result.source_smiles != claim.smiles
        ):
            raise ValueError("canonicalization source does not match claim")
        if report.catalog_action is not self._expected_action(report.kind):
            raise ValueError("report catalog action is not authoritative")
        if report.kind is ResolutionKind.UNRESOLVED:
            raise ValueError("unresolved identity cannot be confirmed")
        if (
            report.kind
            in {
                ResolutionKind.EXACT_STATE,
                ResolutionKind.NEW_STATE,
                ResolutionKind.NEW_COMPOUND,
            }
            and result is None
        ):
            raise ValueError("canonicalization result is required")
        if report.kind in {
            ResolutionKind.ALIAS_ONLY,
            ResolutionKind.AMBIGUOUS,
            ResolutionKind.CONFLICT,
        }:
            actor = self._validate_actor(
                actor, require_user=True, require_rationale=True
            )
        else:
            actor = self._validate_actor(
                actor, require_user=False, require_rationale=False
            )
        self._validate_selection_authority(report, selection)
        if (
            report.kind is ResolutionKind.NEW_COMPOUND
            and result is not None
            and selection.mode is not SelectionMode.NEW_COMPOUND
        ):
            raise ValueError("new compound report requires new compound selection")
        return result, claim, report, selection, actor

    @staticmethod
    def _expected_action(kind: ResolutionKind) -> CatalogAction:
        return {
            ResolutionKind.EXACT_STATE: CatalogAction.REUSE_STATE,
            ResolutionKind.NEW_STATE: CatalogAction.REUSE_COMPOUND,
            ResolutionKind.NEW_COMPOUND: CatalogAction.CREATE_COMPOUND,
            ResolutionKind.ALIAS_ONLY: CatalogAction.NONE,
            ResolutionKind.AMBIGUOUS: CatalogAction.NONE,
            ResolutionKind.CONFLICT: CatalogAction.NONE,
            ResolutionKind.UNRESOLVED: CatalogAction.NONE,
        }[kind]

    @staticmethod
    def _validate_actor(
        actor: IdentityActor,
        *,
        require_user: bool,
        require_rationale: bool | None = None,
    ) -> IdentityActor:
        try:
            actor = IdentityActor.model_validate(actor)
        except (ValidationError, TypeError, ValueError):
            raise ValueError("identity actor is invalid") from None
        if require_rationale is None:
            require_rationale = require_user
        if require_user and actor.kind is not ActorKind.USER:
            raise ValueError("this identity decision requires a user actor")
        if require_rationale and (
            actor.rationale is None or not actor.rationale.strip()
        ):
            raise ValueError("a user actor requires a rationale")
        return actor

    def _validate_live_report(
        self,
        result: CanonicalizationResult | None,
        claim: IdentityClaim,
        report: ResolutionReport,
        selection: IdentitySelection,
        *,
        index: IdentityIndex,
        allow_structure_race: bool = False,
    ) -> bool:
        """Reject a caller-supplied report which is stale at the write boundary."""
        try:
            live = IdentityResolver().resolve(
                result,
                claim,
                index,
            )
        except (ValidationError, TypeError, ValueError):
            raise ValueError("live identity evidence is invalid") from None
        if (
            live.kind is not report.kind
            or live.catalog_action is not report.catalog_action
            or live.catalog_match_dormant != report.catalog_match_dormant
        ):
            if allow_structure_race and self._is_structure_race(report, live, result):
                return True
            raise ValueError("stale resolution report")
        if report.kind is ResolutionKind.NEW_COMPOUND:
            return False
        if selection.mode is not SelectionMode.EXISTING_TARGET:
            raise ValueError("selection does not match live report authority")
        if report.kind in {ResolutionKind.ALIAS_ONLY, ResolutionKind.AMBIGUOUS}:
            valid = any(
                candidate.compound_id == selection.compound_id
                for candidate in live.candidates
            )
        else:
            valid = any(
                candidate.compound_id == selection.compound_id
                and candidate.molecular_state_id == selection.molecular_state_id
                for candidate in live.candidates
            )
        if not valid:
            raise ValueError("stale resolution report")
        return False

    @staticmethod
    def _is_structure_race(
        report: ResolutionReport,
        live: ResolutionReport,
        result: CanonicalizationResult | None,
    ) -> bool:
        if result is None:
            return False
        if report.kind is ResolutionKind.NEW_COMPOUND:
            return live.kind in {
                ResolutionKind.NEW_STATE,
                ResolutionKind.EXACT_STATE,
            }
        return (
            report.kind is ResolutionKind.NEW_STATE
            and live.kind is ResolutionKind.EXACT_STATE
        )

    @staticmethod
    def _reserve_write(uow: UnitOfWork) -> None:
        """Take SQLite's writer reservation before the final authority read."""
        try:
            uow.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        except SQLAlchemyError:
            raise StorageWriteError(
                "identity confirmation could not reserve its write transaction"
            ) from None

    @staticmethod
    def _validate_selection(selection: IdentitySelection) -> IdentitySelection:
        try:
            return IdentitySelection.model_validate(selection)
        except (ValidationError, TypeError, ValueError):
            raise ValueError("identity selection is invalid") from None

    @classmethod
    def _validate_selection_authority(
        cls, report: ResolutionReport, selection: IdentitySelection
    ) -> None:
        if report.kind is ResolutionKind.NEW_COMPOUND:
            if selection.mode is not SelectionMode.NEW_COMPOUND:
                raise ValueError("selection does not match report authority")
            return
        if selection.mode is not SelectionMode.EXISTING_TARGET:
            raise ValueError("selection does not match report authority")
        candidates = report.candidates
        if (
            report.kind in {ResolutionKind.ALIAS_ONLY, ResolutionKind.AMBIGUOUS}
            and selection.molecular_state_id is not None
        ):
            raise ValueError("alias evidence requires a compound-only target")
        if report.kind in {ResolutionKind.ALIAS_ONLY, ResolutionKind.AMBIGUOUS}:
            present = any(
                candidate.compound_id == selection.compound_id
                for candidate in candidates
            )
        else:
            present = any(
                candidate.compound_id == selection.compound_id
                and candidate.molecular_state_id == selection.molecular_state_id
                for candidate in candidates
            )
        if not present:
            raise ValueError("selection is absent from the resolution report")
        if (
            report.kind is ResolutionKind.EXACT_STATE
            and selection.molecular_state_id is None
        ):
            raise ValueError("exact-state report requires its exact state")
        if (
            report.kind is ResolutionKind.NEW_STATE
            and selection.molecular_state_id is not None
        ):
            raise ValueError("new-state report requires its parent compound")

    def _confirm_in_uow(
        self,
        uow: UnitOfWork,
        result: CanonicalizationResult | None,
        claim: IdentityClaim,
        report: ResolutionReport,
        selection: IdentitySelection,
        actor: IdentityActor,
        *,
        reuse_after_race: bool,
    ) -> IdentityResolution:
        assert claim.import_batch_id is not None
        assert claim.source_system is not None
        assert claim.source_value is not None
        batch = uow.import_batches.get(claim.import_batch_id)
        if batch is None:
            raise RecordNotFoundError("import batch was not found")
        if batch.status is ImportStatus.ROLLED_BACK:
            raise ValueError(
                "rolled-back import batch cannot receive identity evidence"
            )
        target_compound: str | None = selection.compound_id
        target_state: str | None = selection.molecular_state_id
        if report.kind is ResolutionKind.NEW_COMPOUND:
            assert result is not None
            existing = uow.compounds.get_by_structure_hash(
                result.compound.structure_hash
            )
            if existing is None:
                uow.compounds.add(result.compound)
                target_compound = result.compound.id
            else:
                target_compound = existing.id
            existing_state = uow.molecular_states.get_by_state_hash(
                result.molecular_state.state_hash
            )
            if existing_state is None:
                state = result.molecular_state.model_copy(
                    update={"compound_id": target_compound}
                )
                uow.molecular_states.add(state)
                self._hit("after_state")
                target_state = state.id
            else:
                if existing_state.compound_id != target_compound:
                    raise ValueError("state hash belongs to another compound")
                target_state = existing_state.id
        elif report.kind is ResolutionKind.NEW_STATE:
            assert result is not None and target_compound is not None
            compound = uow.compounds.get(target_compound)
            if compound is None:
                raise RecordNotFoundError("selected compound was not found")
            if compound.structure_hash != result.compound.structure_hash:
                raise ValueError("result does not match the selected compound")
            existing_state = uow.molecular_states.get_by_state_hash(
                result.molecular_state.state_hash
            )
            if existing_state is not None:
                if existing_state.compound_id != target_compound:
                    raise ValueError("state hash belongs to another compound")
                target_state = existing_state.id
            else:
                state = result.molecular_state.model_copy(
                    update={"compound_id": target_compound}
                )
                uow.molecular_states.add(state)
                self._hit("after_state")
                target_state = state.id
        elif report.kind is ResolutionKind.EXACT_STATE:
            assert (
                result is not None
                and target_compound is not None
                and target_state is not None
            )
            compound = uow.compounds.get(target_compound)
            exact_state = uow.molecular_states.get(target_state)
            if (
                compound is None
                or exact_state is None
                or exact_state.compound_id != compound.id
            ):
                raise RecordNotFoundError("selected identity target was not found")
            if (
                compound.structure_hash != result.compound.structure_hash
                or exact_state.state_hash != result.molecular_state.state_hash
            ):
                raise ValueError("result does not match the selected identity target")
        if report.kind in {
            ResolutionKind.ALIAS_ONLY,
            ResolutionKind.AMBIGUOUS,
            ResolutionKind.CONFLICT,
        }:
            if target_compound is None:
                raise ValueError("a pre-existing compound target is required")
            compound = uow.compounds.get(target_compound)
            if compound is None:
                raise RecordNotFoundError("selected compound was not found")
            if report.kind in {ResolutionKind.ALIAS_ONLY, ResolutionKind.AMBIGUOUS}:
                target_state = None
            elif target_state is not None:
                selected_state = uow.molecular_states.get(target_state)
                if selected_state is None or selected_state.compound_id != compound.id:
                    raise ValueError("selected state is not owned by the compound")
        alias = uow.aliases.add(
            Alias(
                source_system=claim.source_system,
                source_value=claim.source_value,
                import_batch_id=claim.import_batch_id,
                created_at=self._clock(),
            )
        )
        resolution = IdentityResolution(
            alias_id=alias.id,
            decision=IdentityDecision.CONFIRMED,
            compound_id=target_compound,
            molecular_state_id=target_state,
            decided_at=self._clock(),
            actor_kind=actor.kind,
            actor_id=actor.actor_id,
            rationale=actor.rationale,
        )
        uow.identity_resolutions.add(resolution)
        self._hit("after_alias_resolution")
        self._hit("before_audit")
        event = self._audit(
            action="identity.confirmed",
            resolution=resolution,
            batch_id=alias.import_batch_id,
            result=result,
            report=report,
            selection=IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET,
                compound_id=target_compound,
                molecular_state_id=target_state,
            ),
            actor=actor,
            reuse_after_race=reuse_after_race,
        )
        uow.audit_events.add(event)
        return resolution

    def _append_transition(
        self,
        alias_id: str,
        predecessor_id: str,
        selection: IdentitySelection | None,
        actor: IdentityActor,
        *,
        decision: IdentityDecision,
    ) -> IdentityResolution:
        with self._uow_factory() as uow:
            alias = uow.aliases.get(alias_id)
            predecessor = uow.identity_resolutions.get(predecessor_id)
            if alias is None or predecessor is None or predecessor.alias_id != alias_id:
                raise RecordNotFoundError("identity predecessor was not found")
            batch = uow.import_batches.get(alias.import_batch_id)
            if batch is None:
                raise RecordNotFoundError("identity batch was not found")
            if batch.status is ImportStatus.ROLLED_BACK:
                raise ValueError(
                    "rolled-back import batch cannot receive identity evidence"
                )
            history = uow.identity_resolutions.list_by_alias(alias_id)
            if not history or any(
                item.supersedes_id == predecessor_id for item in history
            ):
                raise IdentityResolutionConflictError()
            if decision is IdentityDecision.RETRACTED and predecessor.decision not in {
                IdentityDecision.CONFIRMED,
                IdentityDecision.REASSIGNED,
                IdentityDecision.RESTORED,
            }:
                raise ValueError("only a targeted active decision can be retracted")
            if (
                decision is IdentityDecision.RESTORED
                and predecessor.decision is not IdentityDecision.RETRACTED
            ):
                raise ValueError("restore requires a retracted predecessor")
            compound_id: str | None = None
            state_id: str | None = None
            if decision in {IdentityDecision.REASSIGNED, IdentityDecision.RESTORED}:
                assert selection is not None and selection.compound_id is not None
                compound = uow.compounds.get(selection.compound_id)
                if compound is None:
                    raise RecordNotFoundError("selected compound was not found")
                compound_id = compound.id
                state_id = selection.molecular_state_id
                if state_id is not None:
                    state = uow.molecular_states.get(state_id)
                    if state is None or state.compound_id != compound.id:
                        raise ValueError("selected state is not owned by the compound")
            resolution = IdentityResolution(
                alias_id=alias_id,
                decision=decision,
                compound_id=compound_id,
                molecular_state_id=state_id,
                supersedes_id=predecessor_id,
                decided_at=self._clock(),
                actor_kind=actor.kind,
                actor_id=actor.actor_id,
                rationale=actor.rationale,
            )
            self._hit("before_transition")
            uow.identity_resolutions.add(resolution)
            payload = {
                "prior_target": {
                    "compound_id": predecessor.compound_id,
                    "molecular_state_id": predecessor.molecular_state_id,
                },
                "selected_target": {
                    "compound_id": compound_id,
                    "molecular_state_id": state_id,
                },
                "actor_kind": actor.kind.value,
                "actor_id": actor.actor_id,
                "rationale": actor.rationale,
            }
            uow.audit_events.add(
                AuditEvent(
                    timestamp=self._clock(),
                    action=f"identity.{decision.value}",
                    entity_type="identity_resolution",
                    entity_id=resolution.id,
                    import_batch_id=alias.import_batch_id,
                    old_value_json=canonical_json(payload["prior_target"]),
                    new_value_json=canonical_json(payload),
                    source="identity_service",
                    actor_kind=actor.kind,
                    actor_id=actor.actor_id,
                )
            )
            return resolution

    def _audit(
        self,
        *,
        action: str,
        resolution: IdentityResolution,
        batch_id: str,
        result: CanonicalizationResult | None,
        report: ResolutionReport,
        selection: IdentitySelection,
        actor: IdentityActor,
        reuse_after_race: bool,
    ) -> AuditEvent:
        payload: dict[str, Any] = {
            "policy_id": result.chemistry_policy_id if result else None,
            "chemistry_policy_id": result.chemistry_policy_id if result else None,
            "rdkit_version": result.compound.rdkit_version if result else None,
            "inchi_version": result.compound.inchi_version if result else None,
            "structure_hash": result.compound.structure_hash if result else None,
            "state_hash": result.molecular_state.state_hash if result else None,
            "warnings": [warning.code.value for warning in result.warnings]
            if result
            else [],
            "warning_codes": [warning.code.value for warning in result.warnings]
            if result
            else [],
            "inchi_unavailable": bool(
                result
                and any(
                    warning.code.value == "inchi_unavailable"
                    for warning in result.warnings
                )
            ),
            "report_kind": report.kind.value,
            "catalog_action": report.catalog_action.value,
            "catalog_match_dormant": report.catalog_match_dormant,
            "reuse_after_race": reuse_after_race,
            "selected_target": {
                "compound_id": selection.compound_id,
                "molecular_state_id": selection.molecular_state_id,
            },
            "actor_kind": actor.kind.value,
            "actor_id": actor.actor_id,
            "rationale": actor.rationale,
        }
        return AuditEvent(
            timestamp=self._clock(),
            action=action,
            entity_type="identity_resolution",
            entity_id=resolution.id,
            import_batch_id=batch_id,
            new_value_json=canonical_json(payload),
            source="identity_service",
            actor_kind=actor.kind,
            actor_id=actor.actor_id,
        )

    def _hit(self, name: str) -> None:
        if self._failpoint is not None:
            self._failpoint(name)


__all__ = ["IdentityService"]
