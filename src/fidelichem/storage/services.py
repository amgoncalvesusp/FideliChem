"""Atomic lifecycle services for import batches and audit history."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine

from fidelichem.domain.errors import InvalidStatusTransitionError
from fidelichem.domain.json import canonical_json
from fidelichem.domain.models import (
    ActorKind,
    AuditEvent,
    ImportBatch,
    ImportStatus,
    Project,
)

from .repositories import RecordNotFoundError
from .session import SessionFactory, UnitOfWork

Failpoint = Callable[[str], None]
Clock = Callable[[], datetime]


class _Unset:
    pass


_UNSET = _Unset()


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
            raise InvalidStatusTransitionError("new import batches must be in progress")
        with UnitOfWork(self._session_factory) as uow:
            created = uow.import_batches.add(batch)
            self._trigger("before_audit", failpoint)
            uow.audit_events.add(self._event("import.created", None, created))
            self._trigger("after_audit", failpoint)
        return created

    def update_project(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None | _Unset = _UNSET,
        updated_at: datetime | None = None,
        expected_updated_at: datetime | None = None,
        failpoint: Failpoint | None = None,
    ) -> Project:
        """Update project metadata and append one atomic audit event."""

        with UnitOfWork(self._session_factory) as uow:
            before = self._require_project(uow, project_id)
            candidate_data = before.model_dump()
            if name is not None:
                candidate_data["name"] = name
            if description is not _UNSET:
                candidate_data["description"] = description
            changed = (
                candidate_data["name"] != before.name
                or candidate_data["description"] != before.description
            )
            if changed:
                candidate_data["updated_at"] = updated_at or self._clock()
            else:
                candidate_data["updated_at"] = before.updated_at
            candidate = Project.model_validate(candidate_data)
            if (
                changed
                and updated_at is None
                and candidate.updated_at <= before.updated_at
            ):
                candidate = candidate.model_copy(
                    update={"updated_at": before.updated_at + timedelta(microseconds=1)}
                )
            if not changed:
                return uow.projects.update(
                    candidate,
                    expected_updated_at=expected_updated_at or before.updated_at,
                )
            self._trigger("before_project_update", failpoint)
            updated = uow.projects.update(
                candidate,
                expected_updated_at=expected_updated_at or before.updated_at,
            )
            self._trigger("after_project_update", failpoint)
            self._append_project_audit(uow, before, updated, failpoint)
        return updated

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

    def _append_project_audit(
        self,
        uow: UnitOfWork,
        before: Project,
        after: Project,
        failpoint: Failpoint | None,
    ) -> None:
        self._trigger("before_audit", failpoint)
        uow.audit_events.add(self._project_event("project.updated", before, after))
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

    def _project_event(
        self,
        action: str,
        before: Project,
        after: Project,
    ) -> AuditEvent:
        return AuditEvent(
            timestamp=self._clock(),
            action=action,
            entity_type="project",
            entity_id=after.id,
            old_value_json=self._json(before),
            new_value_json=self._json(after),
            source=self._audit_source,
            actor_kind=self._actor_kind,
            actor_id=self._actor_id,
        )

    @staticmethod
    def _json(value: ImportBatch | Project) -> str:
        return canonical_json(value.model_dump(mode="json"))

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

    @staticmethod
    def _require_project(uow: UnitOfWork, project_id: str) -> Project:
        project = uow.projects.get(project_id)
        if project is None:
            raise RecordNotFoundError("project was not found")
        return project


__all__ = ["StorageService"]
