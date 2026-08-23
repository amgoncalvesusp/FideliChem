"""Import manager orchestrating adapter discovery, validation, and atomic storage."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fidelichem.adapters.base import verify_import_plan
from fidelichem.adapters.registry import AdapterRegistry
from fidelichem.chemistry.service import ChemistryService
from fidelichem.domain.adapters import (
    DetectionReport,
    DockingRunRecord,
    ImportBundle,
    ImportPlan,
    ImportResult,
    QCIssue,
    QCSeverity,
)
from fidelichem.domain.chemistry import (
    CanonicalizationResult,
    IdentityActor,
    IdentityClaim,
    IdentityResolution,
    IdentitySelection,
    SelectionMode,
)
from fidelichem.domain.errors import (
    ChemistryError,
    ImportValidationError,
)
from fidelichem.domain.json import canonical_json
from fidelichem.domain.models import (
    ActorKind,
    AuditEvent,
    ImportBatch,
    ImportStatus,
    SourceArtifact,
)
from fidelichem.identity.models import (
    ResolutionKind,
    ResolutionReport,
)
from fidelichem.identity.resolver import IdentityResolver
from fidelichem.identity.service import IdentityService
from fidelichem.importers.duplicate_detector import DuplicateImportDetector
from fidelichem.storage.identity_index import PersistentIdentityIndex
from fidelichem.storage.session import UnitOfWork

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
UowFactory = Callable[[], UnitOfWork]
Failpoint = Callable[[str], None]


class ImportManager:
    """Coordinates adapter discovery, validation, and batch ingestion."""

    def __init__(
        self,
        registry: AdapterRegistry,
        uow_factory: UowFactory,
        identity_service: IdentityService,
        chemistry_service: ChemistryService,
        *,
        duplicate_detector: DuplicateImportDetector | None = None,
        clock: Clock | None = None,
        failpoint: Failpoint | None = None,
    ) -> None:
        self._registry = registry
        self._uow_factory = uow_factory
        self._identity_service = identity_service
        self._chemistry_service = chemistry_service
        self._duplicate_detector = duplicate_detector or DuplicateImportDetector()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._failpoint = failpoint

    def _hit(self, name: str) -> None:
        if self._failpoint is not None:
            self._failpoint(name)

    def detect(self, source: Path) -> tuple[DetectionReport, ...]:
        """Probe candidate source across all registered adapters and rank results."""
        return self._registry.probe_all(source)

    def plan(
        self,
        adapter_id: str,
        source: Path,
        options: Mapping[str, Any] | None = None,
    ) -> ImportPlan:
        """Create an immutable import plan using the specified adapter."""
        adapter = self._registry.get(adapter_id)
        return adapter.plan(source, options)

    def execute_import(
        self,
        project_id: str,
        plan: ImportPlan,
        *,
        dry_run: bool = False,
        actor: IdentityActor | None = None,
        failpoint: Failpoint | None = None,
    ) -> ImportResult:
        """Execute an import plan through validation and atomic persistence."""
        active_failpoint = failpoint or self._failpoint
        adapter = self._registry.get(plan.adapter_id)

        # 1. Duplicate detection check
        with self._uow_factory() as uow:
            self._duplicate_detector.assert_not_duplicate(uow, project_id, plan)

        # 2. Revalidate the immutable source boundary, then parse the bundle.
        # Adapters perform the same check, but the manager owns the contract
        # and protects custom adapters that implement the protocol directly.
        verify_import_plan(plan)
        bundle = adapter.parse(plan)

        # 3. Validate bundle
        val_report = adapter.validate(bundle)
        if not val_report.is_valid:
            error_details = (
                "; ".join(val_report.errors)
                if val_report.errors
                else "validation failed"
            )
            raise ImportValidationError(f"Import validation failed: {error_details}")

        # Canonicalization is a per-record boundary.  A campaign can contain
        # salts, co-crystals, or structures outside the bounded chemistry
        # policy; those records must remain visible as QC findings without
        # preventing valid neighboring records from being imported.
        canonical_results: list[CanonicalizationResult | None] = []
        chemistry_qc: list[QCIssue] = []
        now = self._clock()
        for compound in bundle.compounds:
            if not compound.source_smiles:
                canonical_results.append(None)
                continue
            try:
                canonical_results.append(
                    self._chemistry_service.canonicalize(
                        compound.source_smiles,
                        preparation_ph=compound.preparation_ph,
                        created_at=now,
                    )
                )
            except ChemistryError as exc:
                canonical_results.append(None)
                chemistry_qc.append(
                    QCIssue(
                        code=f"QC_{exc.diagnostic_code}",
                        message=(
                            f"Compound '{compound.source_value}' was skipped: "
                            f"{exc.message}"
                        ),
                        severity=QCSeverity.WARNING,
                        source_file=compound.source_artifact_path,
                        entity_reference=str(compound.source_value),
                    )
                )

        if chemistry_qc:
            bundle = bundle.model_copy(
                update={
                    "qc_messages": bundle.qc_messages + tuple(chemistry_qc),
                }
            )
            val_report = val_report.model_copy(
                update={
                    "warnings": val_report.warnings
                    + (
                        f"Skipped {len(chemistry_qc)} compounds whose structures "
                        "failed the chemistry identity policy; see QC diagnostics.",
                    ),
                    "qc_issues": bundle.qc_messages,
                }
            )

        # 4. Dry-run early return
        if dry_run:
            simulated_batch = ImportBatch(
                project_id=project_id,
                adapter_id=plan.adapter_id,
                adapter_version=plan.adapter_version,
                started_at=now,
                completed_at=now,
                status=ImportStatus.COMPLETED,
                source_root=plan.source_root,
                file_count=len(bundle.source_artifacts),
                input_hash=plan.plan_hash,
                warnings=val_report.warnings,
            )
            return ImportResult(
                batch=simulated_batch,
                bundle=bundle,
                validation=val_report,
                confirmed_resolutions=(),
            )

        # 5. Atomic persistence of batch, identities, evidence, and audit
        # trail.  A failed import is represented by a clean failed batch in a
        # follow-up transaction; no partial artifacts or scientific rows leak.
        effective_actor = actor or IdentityActor(kind=ActorKind.SYSTEM)
        confirmed_resolutions: list[IdentityResolution] = []
        planned_batch = ImportBatch(
            project_id=project_id,
            adapter_id=plan.adapter_id,
            adapter_version=plan.adapter_version,
            started_at=now,
            source_root=plan.source_root,
            file_count=len(bundle.source_artifacts),
            input_hash=plan.plan_hash,
            warnings=val_report.warnings,
        )

        if active_failpoint:
            active_failpoint("before_batch_creation")

        batch = planned_batch
        try:
            with self._uow_factory() as uow:
                self._identity_service.reserve_write(uow)
                batch = uow.import_batches.add(planned_batch)
                persisted_artifacts = self._persist_source_artifacts(
                    uow, bundle, batch.id, plan, now
                )

                # Resolve and confirm chemical identities for the active batch.
                # Read identity projections through the active UoW session.
                # Opening a second SQLite connection while this transaction is
                # ingesting thousands of rows can hit the database lock and
                # turns a valid import into an opaque StorageReadError.
                index = PersistentIdentityIndex(uow.session)
                resolver = IdentityResolver()
                for compound_index, compound in enumerate(bundle.compounds):
                    canon_result = canonical_results[compound_index]
                    if compound.source_smiles and canon_result is None:
                        continue

                    claim = IdentityClaim(
                        source_system=compound.source_system,
                        source_value=compound.source_value,
                        smiles=compound.source_smiles,
                        inchikey=compound.source_inchikey,
                        import_batch_id=batch.id,
                    )
                    report = resolver.resolve(canon_result, claim, index)
                    selection = self._determine_selection(report)
                    confirmed_resolutions.append(
                        self._identity_service.confirm_claim(
                            canon_result,
                            claim,
                            report,
                            selection,
                            effective_actor,
                            uow=uow,
                        )
                    )

                self._persist_bundle_evidence(
                    uow,
                    bundle,
                    batch_id=batch.id,
                    artifact_ids=persisted_artifacts,
                )

                if active_failpoint:
                    active_failpoint("before_batch_completion")

                completed_batch = uow.import_batches.complete(
                    batch.id, completed_at=now
                )
                uow.audit_events.add(
                    AuditEvent(
                        timestamp=now,
                        action="import.completed",
                        entity_type="import_batch",
                        entity_id=batch.id,
                        import_batch_id=batch.id,
                        new_value_json=canonical_json(
                            {
                                "adapter_id": plan.adapter_id,
                                "adapter_version": plan.adapter_version,
                                "file_count": len(bundle.source_artifacts),
                                "compounds_count": len(bundle.compounds),
                                "targets_count": len(bundle.targets),
                                "docking_runs_count": len(bundle.docking_runs),
                                "poses_count": len(bundle.poses),
                                "scores_count": len(bundle.scores),
                                "interactions_count": len(bundle.interactions),
                                "md_runs_count": len(bundle.md_runs),
                                "md_metrics_count": len(bundle.md_metrics),
                                "plan_hash": plan.plan_hash,
                            }
                        ),
                        source=f"fidelichem.importer.{plan.adapter_id}",
                        actor_kind=effective_actor.kind,
                        actor_id=effective_actor.actor_id,
                    )
                )
        except BaseException as exc:
            # The main UnitOfWork has already rolled back all rows.  Keep a
            # clean lifecycle marker for operators without retaining partial
            # source artifacts, identities, or scientific evidence.
            with self._uow_factory() as uow:
                failed_batch = uow.import_batches.add(
                    planned_batch.model_copy(
                        update={
                            "status": ImportStatus.FAILED,
                            "completed_at": now,
                        }
                    )
                )
                uow.audit_events.add(
                    AuditEvent(
                        timestamp=now,
                        action="import.failed",
                        entity_type="import_batch",
                        entity_id=failed_batch.id,
                        import_batch_id=failed_batch.id,
                        new_value_json=canonical_json(
                            {
                                "error": type(exc).__name__,
                                "plan_hash": plan.plan_hash,
                            }
                        ),
                        source=f"fidelichem.importer.{plan.adapter_id}",
                        actor_kind=effective_actor.kind,
                        actor_id=effective_actor.actor_id,
                    )
                )
            raise

        return ImportResult(
            batch=completed_batch,
            bundle=bundle,
            validation=val_report,
            confirmed_resolutions=tuple(confirmed_resolutions),
        )

    def _persist_source_artifacts(
        self,
        uow: UnitOfWork,
        bundle: ImportBundle,
        batch_id: str,
        plan: ImportPlan,
        now: datetime,
    ) -> dict[str, str]:
        """Persist source metadata and return relative-path to row IDs."""

        artifact_ids: dict[str, str] = {}
        for artifact in bundle.source_artifacts:
            stored = uow.source_artifacts.add(
                SourceArtifact(
                    import_batch_id=batch_id,
                    path=f"{plan.source_root}/{artifact.relative_path}",
                    relative_path=artifact.relative_path,
                    sha256=artifact.sha256,
                    file_type=artifact.file_type,
                    size_bytes=artifact.size_bytes,
                    mtime=artifact.mtime or now,
                )
            )
            artifact_ids[stored.relative_path] = stored.id
        return artifact_ids

    def _persist_bundle_evidence(
        self,
        uow: UnitOfWork,
        bundle: ImportBundle,
        *,
        batch_id: str,
        artifact_ids: Mapping[str, str],
    ) -> None:
        """Persist every canonical evidence family in dependency order."""

        target_ids: dict[str, str] = {}
        for target_record in bundle.targets:
            target_ids[target_record.name] = uow.evidence.add_target(
                target_record,
                import_batch_id=batch_id,
            )

        docking_run_ids: dict[str, str] = {}
        for docking_record in bundle.docking_runs:
            docking_run_ids[docking_record.run_name] = uow.evidence.add_docking_run(
                docking_record,
                import_batch_id=batch_id,
                target_id=target_ids.get(docking_record.target_name or ""),
            )

        # Some producers emit poses/scores without a separate run record.  Do
        # not discard those observations: persist an explicit, traceable
        # placeholder run rather than guessing an engine or configuration.
        orphan_run_names = {pose.run_name for pose in bundle.poses}
        orphan_run_names.update(score.run_name for score in bundle.scores)
        orphan_run_names.difference_update(docking_run_ids)
        for orphan_run_name in sorted(orphan_run_names):
            docking_run_ids[orphan_run_name] = uow.evidence.add_docking_run(
                DockingRunRecord(
                    run_name=orphan_run_name,
                    engine="UNSPECIFIED",
                    parameters={"implicit": True},
                ),
                import_batch_id=batch_id,
            )

        pose_ids: dict[tuple[str, str], str] = {}
        for pose_record in bundle.poses:
            run_id = docking_run_ids.get(pose_record.run_name)
            if run_id is None:
                raise ValueError(
                    f"Pose '{pose_record.source_pose_id}' references an unknown "
                    f"docking run '{pose_record.run_name}'"
                )
            pose_ids[
                (pose_record.run_name, pose_record.source_pose_id)
            ] = uow.evidence.add_pose(
                pose_record,
                import_batch_id=batch_id,
                docking_run_id=run_id,
                source_artifact_id=self._artifact_id(
                    artifact_ids, pose_record.structure_artifact_path
                ),
            )

        for score_record in bundle.scores:
            run_id = docking_run_ids.get(score_record.run_name)
            if run_id is None:
                raise ValueError(
                    f"Score '{score_record.score_key}' references an unknown "
                    f"docking run '{score_record.run_name}'"
                )
            uow.evidence.add_score(
                score_record,
                import_batch_id=batch_id,
                docking_run_id=run_id,
                pose_id=pose_ids.get(
                    (score_record.run_name, score_record.source_pose_id)
                ),
                source_artifact_id=self._artifact_id(
                    artifact_ids, score_record.source_artifact_path
                ),
            )

        for interaction_record in bundle.interactions:
            uow.evidence.add_interaction(
                interaction_record,
                import_batch_id=batch_id,
                docking_run_id=docking_run_ids.get(interaction_record.run_name),
                pose_id=pose_ids.get(
                    (interaction_record.run_name, interaction_record.source_pose_id)
                ),
                target_id=target_ids.get(interaction_record.target_name or ""),
                source_artifact_id=None,
            )

        md_run_ids: dict[str, str] = {}
        for md_run_record in bundle.md_runs:
            md_run_ids[md_run_record.run_name] = uow.evidence.add_md_run(
                md_run_record,
                import_batch_id=batch_id,
                target_id=target_ids.get(md_run_record.target_name or ""),
                pose_id=pose_ids.get(
                    (md_run_record.run_name, md_run_record.source_pose_id or "")
                ),
            )

        for metric_record in bundle.md_metrics:
            md_run_id = md_run_ids.get(metric_record.run_name)
            if md_run_id is None:
                raise ValueError(
                    f"MD metric '{metric_record.metric_key}' references an unknown "
                    f"run '{metric_record.run_name}'"
                )
            uow.evidence.add_md_metric(
                metric_record,
                import_batch_id=batch_id,
                md_run_id=md_run_id,
                source_artifact_id=self._artifact_id(
                    artifact_ids, metric_record.source_artifact_path
                ),
            )

    @staticmethod
    def _artifact_id(
        artifact_ids: Mapping[str, str], relative_path: str | None
    ) -> str | None:
        if relative_path is None:
            return None
        artifact_id = artifact_ids.get(relative_path)
        if artifact_id is None:
            raise ValueError(
                f"Evidence references source artifact '{relative_path}' "
                "outside the import plan"
            )
        return artifact_id

    def rollback_import(
        self,
        project_id: str,
        batch_id: str,
        reason: str,
        *,
        actor: IdentityActor | None = None,
    ) -> ImportBatch:
        """Logically roll back an import batch, recording provenance and audit event."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Rollback reason must be a non-blank string")

        now = self._clock()
        effective_actor = actor or IdentityActor(kind=ActorKind.SYSTEM)

        with self._uow_factory() as uow:
            batch = uow.import_batches.get(batch_id)
            if batch is None or batch.project_id != project_id:
                raise ValueError(
                    f"Import batch '{batch_id}' does not belong to project "
                    f"'{project_id}'"
                )

            rolled_back_batch = uow.import_batches.rollback(
                batch_id,
                rolled_back_at=now,
                rollback_reason=reason.strip(),
            )

            uow.audit_events.add(
                AuditEvent(
                    timestamp=now,
                    action="import.rolled_back",
                    entity_type="import_batch",
                    entity_id=batch_id,
                    import_batch_id=batch_id,
                    new_value_json=canonical_json(
                        {
                            "reason": reason.strip(),
                            "adapter_id": batch.adapter_id,
                        }
                    ),
                    source=f"fidelichem.importer.{batch.adapter_id}",
                    actor_kind=effective_actor.kind,
                    actor_id=effective_actor.actor_id,
                )
            )

            return rolled_back_batch

    def _determine_selection(self, report: ResolutionReport) -> IdentitySelection:
        """Derive authoritative IdentitySelection from resolver report."""
        if report.kind is ResolutionKind.NEW_COMPOUND:
            return IdentitySelection(mode=SelectionMode.NEW_COMPOUND)

        if report.kind in (
            ResolutionKind.EXACT_STATE,
            ResolutionKind.NEW_STATE,
            ResolutionKind.ALIAS_ONLY,
        ):
            if not report.candidates:
                raise ValueError(
                    f"Report {report.kind} requires at least one candidate"
                )
            cand = report.candidates[0]
            state_id = (
                cand.molecular_state_id
                if report.kind is ResolutionKind.EXACT_STATE
                else None
            )
            return IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET,
                compound_id=cand.compound_id,
                molecular_state_id=state_id,
            )

        raise ValueError(
            f"Resolution kind {report.kind.value} requires human confirmation "
            f"or explicit selection"
        )


__all__ = ["ImportManager"]
