"""Atomic lifecycle services for import batches and audit history."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Engine

from fidelichem.domain.errors import InvalidStatusTransitionError
from fidelichem.domain.json import canonical_json
from fidelichem.domain.models import ActorKind, AuditEvent, ImportBatch, ImportStatus

from .repositories import RecordNotFoundError
from .session import SessionFactory, UnitOfWork

Failpoint = Callable[[str], None]
Clock = Callable[[], datetime]


class StorageService:
    """Coordinate lifecycle mutation and its audit event in one UoW."""

    def __init__(
        self,
        session_factory: Engine | SessionFactory,
        *,
        audit_source: str = "storage",
        actor_kind: ActorKind = ActorKind.SYSTEM,
        actor_id: str | None = None,
        clock: Clock | None = None,
        failpoint: Failpoint | None = None,
    ):
        self._session_factory = session_factory
        self._audit_source = audit_source
        self._actor_kind = actor_kind
        self._actor_id = actor_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._failpoint = failpoint

    def create_import_batch(
        self,
        batch: ImportBatch,
        *,
        failpoint: Failpoint | None = None,
    ) -> ImportBatch:
        if batch.status is not ImportStatus.IN_PROGRESS:
            raise InvalidStatusTransitionError(
                "new import batches must be in progress"
            )
        with UnitOfWork(self._session_factory) as uow:
            created = uow.import_batches.add(batch)
            self._trigger("before_audit", failpoint)
            uow.audit_events.add(self._event("import.created", None, created))
            self._trigger("after_audit", failpoint)
        return created

    def complete_import_batch(
        self,
        batch_id: str,
        *,
        completed_at: datetime | None = None,
        expected_status: ImportStatus = ImportStatus.IN_PROGRESS,
        failpoint: Failpoint | None = None,
    ) -> ImportBatch:
        with UnitOfWork(self._session_factory) as uow:
            before = self._require_batch(uow, batch_id)
            self._trigger("before_lifecycle", failpoint)
            completed = uow.import_batches.complete(
                batch_id,
                completed_at=completed_at or self._clock(),
                expected_status=expected_status,
            )
            self._trigger("after_lifecycle", failpoint)
            self._append_audit(
                uow,
                "import.completed",
                before,
                completed,
                failpoint,
            )
        return completed

    def fail_import_batch(
        self,
        batch_id: str,
        *,
        completed_at: datetime | None = None,
        expected_status: ImportStatus = ImportStatus.IN_PROGRESS,
        failpoint: Failpoint | None = None,
    ) -> ImportBatch:
        with UnitOfWork(self._session_factory) as uow:
            before = self._require_batch(uow, batch_id)
            self._trigger("before_lifecycle", failpoint)
            failed = uow.import_batches.fail(
                batch_id,
                completed_at=completed_at or self._clock(),
                expected_status=expected_status,
            )
            self._trigger("after_lifecycle", failpoint)
            self._append_audit(uow, "import.failed", before, failed, failpoint)
        return failed

    def rollback_import_batch(
        self,
        batch_id: str,
        *,
        rolled_back_at: datetime | None = None,
        reason: str | None = None,
        expected_statuses: tuple[ImportStatus, ...] = (
            ImportStatus.COMPLETED,
            ImportStatus.FAILED,
        ),
        failpoint: Failpoint | None = None,
    ) -> ImportBatch:
        with UnitOfWork(self._session_factory) as uow:
            before = self._require_batch(uow, batch_id)
            if before.status is ImportStatus.ROLLED_BACK:
                return before
            self._trigger("before_lifecycle", failpoint)
            rolled_back = uow.import_batches.rollback(
                batch_id,
                rolled_back_at=rolled_back_at or self._clock(),
                rollback_reason=reason,
                expected_statuses=expected_statuses,
            )
            self._trigger("after_lifecycle", failpoint)
            self._append_audit(
                uow,
                "import.rolled_back",
                before,
                rolled_back,
                failpoint,
            )
        return rolled_back

    def _append_audit(
        self,
        uow: UnitOfWork,
        action: str,
        before: ImportBatch,
        after: ImportBatch,
        failpoint: Failpoint | None,
    ) -> None:
        self._trigger("before_audit", failpoint)
        uow.audit_events.add(self._event(action, before, after))
        self._trigger("after_audit", failpoint)

    def _event(
        self,
        action: str,
        before: ImportBatch | None,
        after: ImportBatch,
    ) -> AuditEvent:
        return AuditEvent(
            timestamp=self._clock(),
            action=action,
            entity_type="import_batch",
            entity_id=after.id,
            import_batch_id=after.id,
            old_value_json=None if before is None else self._json(before),
            new_value_json=self._json(after),
            source=self._audit_source,
            actor_kind=self._actor_kind,
            actor_id=self._actor_id,
        )

    @staticmethod
    def _json(batch: ImportBatch) -> str:
        return canonical_json(batch.model_dump(mode="json"))

    def _trigger(self, stage: str, local_failpoint: Failpoint | None) -> None:
        callback = local_failpoint or self._failpoint
        if callback is not None:
            callback(stage)

    @staticmethod
    def _require_batch(uow: UnitOfWork, batch_id: str) -> ImportBatch:
        batch = uow.import_batches.get(batch_id)
        if batch is None:
            raise RecordNotFoundError("import batch was not found")
        return batch


__all__ = ["StorageService"]
