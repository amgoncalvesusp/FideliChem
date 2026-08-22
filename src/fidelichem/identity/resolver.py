"""Pure, read-only identity evidence resolution."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import ValidationError

from fidelichem.domain.chemistry import CanonicalizationResult, IdentityClaim

from .models import (
    CatalogAction,
    EvidenceKind,
    IdentityIndex,
    ResolutionCandidate,
    ResolutionKind,
    ResolutionReason,
    ResolutionReport,
)


def _candidate_key(
    candidate: ResolutionCandidate,
) -> tuple[str, str | None, str | None]:
    return (
        candidate.compound_id,
        candidate.molecular_state_id,
        candidate.resolution_id,
    )


def _merge_candidates(
    groups: Iterable[Iterable[ResolutionCandidate]],
) -> tuple[ResolutionCandidate, ...]:
    merged: dict[
        tuple[str, str | None, str | None], tuple[set[EvidenceKind], bool]
    ] = {}
    for group in groups:
        for candidate in group:
            key = _candidate_key(candidate)
            evidence, dormant = merged.get(key, (set(), False))
            merged = merged | {
                key: (
                    evidence | set(candidate.evidence),
                    dormant or candidate.catalog_dormant,
                )
            }
    return tuple(
        ResolutionCandidate(
            compound_id=compound_id,
            molecular_state_id=state_id,
            resolution_id=resolution_id,
            evidence=tuple(evidence),
            catalog_dormant=dormant,
        )
        for (compound_id, state_id, resolution_id), (evidence, dormant) in (
            merged.items()
        )
    )


def _distinct_targets(
    candidates: Iterable[ResolutionCandidate],
) -> set[tuple[str, str | None]]:
    return {
        (candidate.compound_id, candidate.molecular_state_id)
        for candidate in candidates
    }


def _report(
    kind: ResolutionKind,
    reason: ResolutionReason,
    candidates: Iterable[ResolutionCandidate] = (),
    *,
    dormant: bool = False,
) -> ResolutionReport:
    action = {
        ResolutionKind.EXACT_STATE: CatalogAction.REUSE_STATE,
        ResolutionKind.NEW_STATE: CatalogAction.REUSE_COMPOUND,
        ResolutionKind.NEW_COMPOUND: CatalogAction.CREATE_COMPOUND,
        ResolutionKind.ALIAS_ONLY: CatalogAction.NONE,
        ResolutionKind.AMBIGUOUS: CatalogAction.NONE,
        ResolutionKind.CONFLICT: CatalogAction.NONE,
        ResolutionKind.UNRESOLVED: CatalogAction.NONE,
    }[kind]
    return ResolutionReport(
        kind=kind,
        reason=reason,
        candidates=tuple(candidates),
        catalog_action=action,
        catalog_match_dormant=dormant,
    )


class IdentityResolver:
    """Resolve immutable chemistry and alias evidence without side effects."""

    def resolve(
        self,
        result: CanonicalizationResult | None,
        claim: IdentityClaim,
        index: IdentityIndex,
    ) -> ResolutionReport:
        if not isinstance(claim, IdentityClaim):
            raise TypeError("claim must be an IdentityClaim")
        if result is not None and not isinstance(result, CanonicalizationResult):
            raise TypeError("result must be a CanonicalizationResult or None")
        try:
            claim = IdentityClaim.model_validate(claim)
            if result is not None:
                result = CanonicalizationResult.model_validate(result)
        except (ValidationError, AttributeError, TypeError, ValueError):
            raise ValueError("identity evidence is invalid") from None
        if (
            result is not None
            and claim.smiles is not None
            and result.source_smiles != claim.smiles
        ):
            raise ValueError("canonicalization source does not match the claim")
        if result is None and claim.smiles is not None:
            raise ValueError("canonicalization result is required for a SMILES claim")
        aliases = self._alias_candidates(claim, index)
        supplied_inchi = self._inchi_candidates(claim.inchikey, index)
        if result is None:
            weak_candidates = _merge_candidates((aliases, supplied_inchi))
            if aliases:
                if len(_distinct_targets(aliases)) == 1:
                    return _report(
                        ResolutionKind.ALIAS_ONLY,
                        ResolutionReason.ALIAS_ONLY,
                        weak_candidates,
                    )
                return _report(
                    ResolutionKind.AMBIGUOUS,
                    ResolutionReason.AMBIGUOUS_ALIAS,
                    weak_candidates,
                )
            return _report(
                ResolutionKind.UNRESOLVED,
                ResolutionReason.UNRESOLVED,
                weak_candidates,
            )

        generated_state_key = result.molecular_state.state_inchikey
        external_inchi_conflict = (
            claim.inchikey is not None
            and generated_state_key is not None
            and claim.inchikey != generated_state_key
        )

        state_candidates = index.catalog_by_state_hash(
            result.molecular_state.state_hash
        )
        parent_candidates = index.catalog_by_parent_hash(result.compound.structure_hash)
        generated_inchi_candidates = self._inchi_candidates_for_result(
            result, index, excluded_key=claim.inchikey
        )
        inchi_candidates = _merge_candidates(
            (supplied_inchi, generated_inchi_candidates)
        )
        structural = _merge_candidates((state_candidates, parent_candidates))
        all_candidates = _merge_candidates(
            (state_candidates, parent_candidates, inchi_candidates, aliases)
        )
        if external_inchi_conflict:
            return _report(
                ResolutionKind.CONFLICT,
                ResolutionReason.CONFLICTING_EVIDENCE,
                all_candidates,
            )
        if aliases and self._alias_conflicts(aliases, structural):
            return _report(
                ResolutionKind.CONFLICT,
                ResolutionReason.CONFLICTING_EVIDENCE,
                all_candidates,
            )

        state_targets = _distinct_targets(state_candidates)
        if len(state_targets) > 1:
            return _report(
                ResolutionKind.AMBIGUOUS,
                ResolutionReason.AMBIGUOUS_ALIAS,
                all_candidates,
            )
        if state_targets:
            return _report(
                ResolutionKind.EXACT_STATE,
                ResolutionReason.EXACT_STATE,
                all_candidates,
                dormant=all(
                    candidate.catalog_dormant for candidate in state_candidates
                ),
            )

        parent_targets = {candidate.compound_id for candidate in parent_candidates}
        if len(parent_targets) > 1:
            return _report(
                ResolutionKind.AMBIGUOUS,
                ResolutionReason.AMBIGUOUS_ALIAS,
                all_candidates,
            )
        if parent_targets:
            return _report(
                ResolutionKind.NEW_STATE,
                ResolutionReason.PARENT_MATCH,
                all_candidates,
                dormant=all(
                    candidate.catalog_dormant for candidate in parent_candidates
                ),
            )
        return _report(
            ResolutionKind.NEW_COMPOUND,
            ResolutionReason.NEW_COMPOUND,
            all_candidates,
        )

    @staticmethod
    def _alias_candidates(
        claim: IdentityClaim, index: IdentityIndex
    ) -> tuple[ResolutionCandidate, ...]:
        if claim.source_system is None or claim.source_value is None:
            return ()
        return index.active_by_alias(claim.source_system, claim.source_value)

    @staticmethod
    def _inchi_candidates(
        inchikey: str | None, index: IdentityIndex
    ) -> tuple[ResolutionCandidate, ...]:
        if inchikey is None:
            return ()
        return index.catalog_by_generated_inchikey(inchikey)

    @classmethod
    def _inchi_candidates_for_result(
        cls,
        result: CanonicalizationResult,
        index: IdentityIndex,
        *,
        excluded_key: str | None = None,
    ) -> tuple[ResolutionCandidate, ...]:
        keys = {
            key
            for key in (
                result.molecular_state.state_inchikey,
                result.compound.inchikey,
            )
            if key is not None and key != excluded_key
        }
        return _merge_candidates(
            cls._inchi_candidates(key, index) for key in sorted(keys)
        )

    @staticmethod
    def _alias_conflicts(
        aliases: Iterable[ResolutionCandidate],
        structural: Iterable[ResolutionCandidate],
    ) -> bool:
        structural_candidates = tuple(structural)
        if not structural_candidates:
            return True
        for alias in aliases:
            if alias.molecular_state_id is None:
                compatible = any(
                    alias.compound_id == candidate.compound_id
                    for candidate in structural_candidates
                )
            else:
                compatible = any(
                    alias.compound_id == candidate.compound_id
                    and alias.molecular_state_id == candidate.molecular_state_id
                    for candidate in structural_candidates
                )
            if not compatible:
                return True
        return False


__all__ = ["IdentityResolver"]
