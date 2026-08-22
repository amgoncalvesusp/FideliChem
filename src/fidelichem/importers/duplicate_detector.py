"""Duplicate import detection against completed project batches and artifacts."""

from __future__ import annotations

from fidelichem.domain.adapters import ImportPlan
from fidelichem.domain.errors import DuplicateImportError
from fidelichem.domain.models import ImportBatch, ImportStatus
from fidelichem.storage.session import UnitOfWork


class DuplicateImportDetector:
    """Detects whether an import plan duplicates an active, completed batch."""

    def check_duplicate(
        self,
        uow: UnitOfWork,
        project_id: str,
        plan: ImportPlan,
    ) -> ImportBatch | None:
        """Return existing completed batch if plan is duplicate, else None."""
        completed_batches = uow.import_batches.list_by_project(
            project_id, status=ImportStatus.COMPLETED
        )
        if not completed_batches:
            return None

        # Check 1: exact input_hash match on plan_hash
        for batch in completed_batches:
            if batch.input_hash and batch.input_hash == plan.plan_hash:
                return batch

        # Check 2: exact set of source artifact hashes match
        if plan.file_hashes:
            plan_artifact_set = frozenset(plan.file_hashes)
            for batch in completed_batches:
                batch_artifacts = uow.source_artifacts.list_by_batch(batch.id)
                if batch_artifacts:
                    batch_artifact_set = frozenset(
                        (a.relative_path, a.sha256) for a in batch_artifacts
                    )
                    if batch_artifact_set == plan_artifact_set:
                        return batch

        return None

    def assert_not_duplicate(
        self,
        uow: UnitOfWork,
        project_id: str,
        plan: ImportPlan,
    ) -> None:
        """Raise DuplicateImportError if a duplicate completed batch exists."""
        dup = self.check_duplicate(uow, project_id, plan)
        if dup is not None:
            raise DuplicateImportError(
                f"Duplicate import detected: evidence was already imported in "
                f"completed batch {dup.id}"
            )


__all__ = ["DuplicateImportDetector"]
