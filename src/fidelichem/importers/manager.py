"""Import manager orchestrating adapter discovery, validation, and atomic storage."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fidelichem.adapters.registry import AdapterRegistry
from fidelichem.chemistry.service import ChemistryService
from fidelichem.domain.adapters import (
    DetectionReport,
    ImportPlan,
    ImportResult,
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

        # 2. Parse bundle
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

        now = self._clock()

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

        # 5. Atomic persistence of batch, artifacts, identities, and audit trail
        effective_actor = actor or IdentityActor(kind=ActorKind.SYSTEM)
        confirmed_resolutions: list[IdentityResolution] = []

        if active_failpoint:
            active_failpoint("before_batch_creation")

        with self._uow_factory() as uow:
            batch = uow.import_batches.add(
                ImportBatch(
                    project_id=project_id,
                    adapter_id=plan.adapter_id,
                    adapter_version=plan.adapter_version,
                    started_at=now,
                    source_root=plan.source_root,
                    file_count=len(bundle.source_artifacts),
                    input_hash=plan.plan_hash,
                    warnings=val_report.warnings,
                )
            )

            # Persist source artifacts
            for artifact in bundle.source_artifacts:
                uow.source_artifacts.add(
                    SourceArtifact(
                        import_batch_id=batch.id,
                        path=f"{plan.source_root}/{artifact.relative_path}",
                        relative_path=artifact.relative_path,
                        sha256=artifact.sha256,
                        file_type=artifact.file_type,
                        size_bytes=artifact.size_bytes,
                        mtime=artifact.mtime or now,
                    )
                )

        try:
            # 6. Resolve and confirm chemical identities for the active batch
            index = self._identity_service._index_factory()
            resolver = IdentityResolver()

            for compound in bundle.compounds:
                canon_result: CanonicalizationResult | None = None
                if compound.source_smiles:
                    canon_result = self._chemistry_service.canonicalize(
                        compound.source_smiles,
                        created_at=now,
                    )

                claim = IdentityClaim(
                    source_system=compound.source_system,
                    source_value=compound.source_value,
                    smiles=compound.source_smiles,
                    inchikey=compound.source_inchikey,
                    import_batch_id=batch.id,
                )

                report = resolver.resolve(canon_result, claim, index)
                selection = self._determine_selection(report)

                resolution = self._identity_service.confirm_claim(
                    canon_result,
                    claim,
                    report,
                    selection,
                    effective_actor,
                )
                confirmed_resolutions.append(resolution)

            if active_failpoint:
                active_failpoint("before_batch_completion")

            # 7. Complete batch and write audit event
            with self._uow_factory() as uow:
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
                                "plan_hash": plan.plan_hash,
                            }
                        ),
                        source=f"fidelichem.importer.{plan.adapter_id}",
                        actor_kind=effective_actor.kind,
                        actor_id=effective_actor.actor_id,
                    )
                )
        except BaseException as exc:
            with self._uow_factory() as uow:
                uow.import_batches.fail(batch.id, completed_at=now)
                uow.audit_events.add(
                    AuditEvent(
                        timestamp=now,
                        action="import.failed",
                        entity_type="import_batch",
                        entity_id=batch.id,
                        import_batch_id=batch.id,
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
            return IdentitySelection(
                mode=SelectionMode.EXISTING_TARGET,
                compound_id=cand.compound_id,
                molecular_state_id=cand.molecular_state_id,
            )

        raise ValueError(
            f"Resolution kind {report.kind.value} requires human confirmation "
            f"or explicit selection"
        )


__all__ = ["ImportManager"]
