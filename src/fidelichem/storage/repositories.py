"""Entity-specific repositories for the Phase 1 storage schema."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fidelichem.domain.json import canonical_json
from fidelichem.domain.models import (
    ActorKind,
    AuditEvent,
    ImportBatch,
    ImportStatus,
    Project,
    SourceArtifact,
)

from .orm import (
    _AuditEventRow,
    _ImportBatchRow,
    _ProjectRow,
    _SourceArtifactRow,
)
from .session import StorageError


class RepositoryError(StorageError):
    """Base class for failures raised by a repository operation."""


class DuplicateRecordError(RepositoryError):
    """A primary key or entity-specific unique key already exists."""


class ForeignKeyViolationError(RepositoryError):
    """A referenced parent record does not exist."""


class StorageIntegrityError(RepositoryError):
    """A database integrity rule rejected a repository write."""


def _safe_integrity_error(
    error: IntegrityError,
    *,
    entity: str,
    operation: str,
) -> RepositoryError:
    """Translate SQLAlchemy details without exposing SQL or file paths."""

    detail = str(error.orig).lower()
    if "foreign key" in detail:
        return ForeignKeyViolationError(
            f"{entity} {operation} references a missing parent"
        )
    if "unique" in detail or "primary key" in detail or "only one project" in detail:
        return DuplicateRecordError(f"{entity} already exists")
    return StorageIntegrityError(f"{entity} {operation} violates storage integrity")


def _flush(session: Session, row: object, *, entity: str, operation: str) -> None:
    """Flush a new row while leaving transaction rollback to its owner."""

    try:
        session.add(row)
        session.flush()
    except IntegrityError as error:
        # Do not call rollback here.  The unit of work must own the complete
        # rollback so earlier writes in the same operation are also undone.
        raise _safe_integrity_error(error, entity=entity, operation=operation) from None


def _project_model(row: _ProjectRow) -> Project:
    return Project(
        id=row.id,
        name=row.name,
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
        schema_version=row.schema_version,
    )


def _batch_model(row: _ImportBatchRow) -> ImportBatch:
    parsed_warnings = json.loads(row.warnings_json)
    return ImportBatch(
        id=row.id,
        project_id=row.project_id,
        adapter_id=row.adapter_id,
        adapter_version=row.adapter_version,
        started_at=row.started_at,
        completed_at=row.completed_at,
        status=ImportStatus(row.status),
        source_root=row.source_root,
        file_count=row.file_count,
        input_hash=row.input_hash,
        warnings=tuple(parsed_warnings),
        rolled_back_at=row.rolled_back_at,
        rollback_reason=row.rollback_reason,
    )


def _artifact_model(row: _SourceArtifactRow) -> SourceArtifact:
    return SourceArtifact(
        id=row.id,
        import_batch_id=row.import_batch_id,
        path=row.path,
        relative_path=row.relative_path,
        sha256=row.sha256,
        file_type=row.file_type,
        size_bytes=row.size_bytes,
        mtime=row.mtime,
    )


def _audit_model(row: _AuditEventRow) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        sequence=row.sequence,
        timestamp=row.timestamp,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        import_batch_id=row.import_batch_id,
        old_value_json=row.old_value_json,
        new_value_json=row.new_value_json,
        source=row.source,
        actor_kind=ActorKind(row.actor_kind),
        actor_id=row.actor_id,
    )


class ProjectRepository:
    """Create and read the singleton project row."""

    def __init__(self, session: Session):
        self._session = session

    def add(self, project: Project) -> Project:
        row = _ProjectRow(
            id=project.id,
            name=project.name,
            description=project.description,
            created_at=project.created_at,
            updated_at=project.updated_at,
            schema_version=project.schema_version,
        )
        _flush(self._session, row, entity="project", operation="insert")
        return _project_model(row)

    def get(self, project_id: str | None = None) -> Project | None:
        statement = select(_ProjectRow)
        if project_id is not None:
            statement = statement.where(_ProjectRow.id == project_id)
        row = self._session.execute(statement).scalar_one_or_none()
        return None if row is None else _project_model(row)


class ImportBatchRepository:
    """Create and read immutable import-batch identity and provenance."""

    def __init__(self, session: Session):
        self._session = session

    def add(self, batch: ImportBatch) -> ImportBatch:
        row = _ImportBatchRow(
            id=batch.id,
            project_id=batch.project_id,
            adapter_id=batch.adapter_id,
            adapter_version=batch.adapter_version,
            started_at=batch.started_at,
            completed_at=batch.completed_at,
            status=batch.status.value,
            source_root=batch.source_root,
            file_count=batch.file_count,
            input_hash=batch.input_hash,
            warnings_json=canonical_json(list(batch.warnings)),
            rolled_back_at=batch.rolled_back_at,
            rollback_reason=batch.rollback_reason,
        )
        _flush(self._session, row, entity="import batch", operation="insert")
        return _batch_model(row)

    def get(self, batch_id: str) -> ImportBatch | None:
        row = self._session.get(_ImportBatchRow, batch_id)
        return None if row is None else _batch_model(row)


class SourceArtifactRepository:
    """Append-only source-artifact repository."""

    def __init__(self, session: Session):
        self._session = session

    def add(self, artifact: SourceArtifact) -> SourceArtifact:
        row = _SourceArtifactRow(
            id=artifact.id,
            import_batch_id=artifact.import_batch_id,
            path=artifact.path,
            relative_path=artifact.relative_path,
            sha256=artifact.sha256,
            file_type=artifact.file_type,
            size_bytes=artifact.size_bytes,
            mtime=artifact.mtime,
        )
        _flush(self._session, row, entity="source artifact", operation="insert")
        return _artifact_model(row)

    def get(self, artifact_id: str) -> SourceArtifact | None:
        row = self._session.get(_SourceArtifactRow, artifact_id)
        return None if row is None else _artifact_model(row)

    def list_by_batch(self, batch_id: str) -> tuple[SourceArtifact, ...]:
        statement = (
            select(_SourceArtifactRow)
            .where(_SourceArtifactRow.import_batch_id == batch_id)
            .order_by(_SourceArtifactRow.relative_path, _SourceArtifactRow.id)
        )
        rows = self._session.execute(statement).scalars().all()
        return tuple(_artifact_model(row) for row in rows)


class AuditRepository:
    """Append-only audit-event repository with DB-generated ordering."""

    def __init__(self, session: Session):
        self._session = session

    def add(self, event: AuditEvent) -> AuditEvent:
        row = _AuditEventRow(
            id=event.id,
            # Sequence is intentionally omitted: SQLite owns its ordering.
            timestamp=event.timestamp,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            import_batch_id=event.import_batch_id,
            old_value_json=event.old_value_json,
            new_value_json=event.new_value_json,
            source=event.source,
            actor_kind=event.actor_kind.value,
            actor_id=event.actor_id,
        )
        _flush(self._session, row, entity="audit event", operation="insert")
        self._session.refresh(row)
        return _audit_model(row)

    def get(self, event_id: str) -> AuditEvent | None:
        row = self._session.get(_AuditEventRow, event_id)
        return None if row is None else _audit_model(row)

    def list_events(
        self,
        import_batch_id: str | None = None,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> tuple[AuditEvent, ...]:
        statement = select(_AuditEventRow).order_by(_AuditEventRow.sequence)
        if import_batch_id is not None:
            statement = statement.where(
                _AuditEventRow.import_batch_id == import_batch_id
            )
        if entity_type is not None:
            statement = statement.where(_AuditEventRow.entity_type == entity_type)
        if entity_id is not None:
            statement = statement.where(_AuditEventRow.entity_id == entity_id)
        rows = self._session.execute(statement).scalars().all()
        return tuple(_audit_model(row) for row in rows)

    def list_by_batch(self, batch_id: str) -> tuple[AuditEvent, ...]:
        """Return audit history correlated with one import batch."""

        return self.list_events(batch_id)


__all__ = [
    "AuditRepository",
    "DuplicateRecordError",
    "ForeignKeyViolationError",
    "ImportBatchRepository",
    "ProjectRepository",
    "RepositoryError",
    "SourceArtifactRepository",
    "StorageIntegrityError",
]
