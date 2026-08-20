"""Entity-specific repositories for the Phase 1 storage schema."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import suppress

from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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
from .session import (
    TRANSACTION_FAILED_FLAG,
    UNIT_OF_WORK_FAILED_FLAG,
    UNIT_OF_WORK_FLAG,
    StorageError,
    UnitOfWorkError,
)


class RepositoryError(StorageError):
    """Base class for failures raised by a repository operation."""


class DuplicateRecordError(RepositoryError):
    """A primary key or entity-specific unique key already exists."""


class ForeignKeyViolationError(RepositoryError):
    """A referenced parent record does not exist."""


class StorageIntegrityError(RepositoryError):
    """A database integrity rule rejected a repository write."""


class StorageWriteError(RepositoryError):
    """A non-integrity database failure rejected a repository write."""


class CorruptStoredDataError(RepositoryError):
    """A persisted row cannot be converted into its public domain value."""


_ROLLBACK_LISTENER_FLAG = "_fidelichem_rollback_listener"
_IGNORE_AUTO_ROLLBACK_FLAG = "_fidelichem_ignore_auto_rollback"


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
        _fail_transaction(session)
        raise _safe_integrity_error(error, entity=entity, operation=operation) from None
    except SQLAlchemyError:
        _fail_transaction(session)
        raise StorageWriteError(
            f"{entity} {operation} failed due to a storage error"
        ) from None


def _fail_transaction(session: Session) -> None:
    session.info[TRANSACTION_FAILED_FLAG] = True
    is_unit_of_work = bool(session.info.get(UNIT_OF_WORK_FLAG, False))
    if is_unit_of_work:
        session.info[UNIT_OF_WORK_FAILED_FLAG] = True
    _install_rollback_recovery(session)
    session.info[_IGNORE_AUTO_ROLLBACK_FLAG] = True
    with suppress(BaseException):
        session.rollback()
    # A flush failure may already have ended SQLAlchemy's transaction before
    # this rollback call, so no event is guaranteed.  Consume the guard here;
    # a later explicit caller rollback must be allowed to clear the marker.
    session.info.pop(_IGNORE_AUTO_ROLLBACK_FLAG, None)
    if not is_unit_of_work:
        with suppress(BaseException):
            # Keep a clean transaction open so an explicit caller-owned
            # rollback emits SQLAlchemy's recovery event.
            session.begin()


def _install_rollback_recovery(session: Session) -> None:
    if session.info.get(_ROLLBACK_LISTENER_FLAG, False):
        return

    def clear_caller_failure(rolled_back_session: Session) -> None:
        if rolled_back_session.info.pop(_IGNORE_AUTO_ROLLBACK_FLAG, False):
            return
        if not rolled_back_session.info.get(UNIT_OF_WORK_FLAG, False):
            rolled_back_session.info.pop(TRANSACTION_FAILED_FLAG, None)

    event.listen(session, "after_rollback", clear_caller_failure)
    session.info[_ROLLBACK_LISTENER_FLAG] = True


def _safe_read[ModelT](entity: str, operation: Callable[[], ModelT]) -> ModelT:
    try:
        return operation()
    except CorruptStoredDataError:
        raise
    except Exception:
        raise CorruptStoredDataError(f"stored {entity} data is invalid") from None


def _project_model(row: _ProjectRow) -> Project:
    return _safe_read(
        "project",
        lambda: Project(
            id=row.id,
            name=row.name,
            description=row.description,
            created_at=row.created_at,
            updated_at=row.updated_at,
            schema_version=row.schema_version,
        ),
    )


def _batch_model(row: _ImportBatchRow) -> ImportBatch:
    def convert() -> ImportBatch:
        parsed_warnings = json.loads(row.warnings_json)
        if not isinstance(parsed_warnings, list) or not all(
            isinstance(item, str) for item in parsed_warnings
        ):
            raise ValueError("warnings must be a JSON string array")
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

    return _safe_read("import batch", convert)


def _artifact_model(row: _SourceArtifactRow) -> SourceArtifact:
    return _safe_read(
        "source artifact",
        lambda: SourceArtifact(
            id=row.id,
            import_batch_id=row.import_batch_id,
            path=row.path,
            relative_path=row.relative_path,
            sha256=row.sha256,
            file_type=row.file_type,
            size_bytes=row.size_bytes,
            mtime=row.mtime,
        ),
    )


def _audit_model(row: _AuditEventRow) -> AuditEvent:
    return _safe_read(
        "audit event",
        lambda: AuditEvent(
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
        ),
    )


class _RepositoryBase:
    """Session-bound repository lifecycle shared by concrete repositories."""

    def __init__(self, session: Session):
        self._session: Session | None = session

    def _require_session(self) -> Session:
        session = self._session
        if session is None:
            raise UnitOfWorkError("repository is inactive")
        if session.info.get(TRANSACTION_FAILED_FLAG, False):
            raise UnitOfWorkError("repository transaction has failed")
        return session

    def _deactivate(self) -> None:
        self._session = None


class ProjectRepository(_RepositoryBase):
    """Create and read the singleton project row."""

    def __init__(self, session: Session):
        super().__init__(session)

    def add(self, project: Project) -> Project:
        session = self._require_session()
        row = _ProjectRow(
            id=project.id,
            name=project.name,
            description=project.description,
            created_at=project.created_at,
            updated_at=project.updated_at,
            schema_version=project.schema_version,
        )
        _flush(session, row, entity="project", operation="insert")
        return _project_model(row)

    def get(self, project_id: str | None = None) -> Project | None:
        session = self._require_session()
        statement = select(_ProjectRow)
        if project_id is not None:
            statement = statement.where(_ProjectRow.id == project_id)
        return _safe_read(
            "project",
            lambda: (
                lambda row: None if row is None else _project_model(row)
            )(session.execute(statement).scalar_one_or_none()),
        )


class ImportBatchRepository(_RepositoryBase):
    """Create and read immutable import-batch identity and provenance."""

    def __init__(self, session: Session):
        super().__init__(session)

    def add(self, batch: ImportBatch) -> ImportBatch:
        session = self._require_session()
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
        _flush(session, row, entity="import batch", operation="insert")
        return _batch_model(row)

    def get(self, batch_id: str) -> ImportBatch | None:
        session = self._require_session()
        return _safe_read(
            "import batch",
            lambda: (
                lambda row: None if row is None else _batch_model(row)
            )(session.get(_ImportBatchRow, batch_id)),
        )


class SourceArtifactRepository(_RepositoryBase):
    """Append-only source-artifact repository."""

    def __init__(self, session: Session):
        super().__init__(session)

    def add(self, artifact: SourceArtifact) -> SourceArtifact:
        session = self._require_session()
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
        _flush(session, row, entity="source artifact", operation="insert")
        return _artifact_model(row)

    def get(self, artifact_id: str) -> SourceArtifact | None:
        session = self._require_session()
        return _safe_read(
            "source artifact",
            lambda: (
                lambda row: None if row is None else _artifact_model(row)
            )(session.get(_SourceArtifactRow, artifact_id)),
        )

    def list_by_batch(self, batch_id: str) -> tuple[SourceArtifact, ...]:
        session = self._require_session()
        statement = (
            select(_SourceArtifactRow)
            .where(_SourceArtifactRow.import_batch_id == batch_id)
            .order_by(_SourceArtifactRow.relative_path, _SourceArtifactRow.id)
        )
        return _safe_read(
            "source artifact",
            lambda: tuple(
                _artifact_model(row)
                for row in session.execute(statement).scalars().all()
            ),
        )


class AuditRepository(_RepositoryBase):
    """Append-only audit-event repository with DB-generated ordering."""

    def __init__(self, session: Session):
        super().__init__(session)

    def add(self, event: AuditEvent) -> AuditEvent:
        session = self._require_session()
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
        _flush(session, row, entity="audit event", operation="insert")
        session.refresh(row)
        return _audit_model(row)

    def get(self, event_id: str) -> AuditEvent | None:
        session = self._require_session()
        return _safe_read(
            "audit event",
            lambda: (
                lambda row: None if row is None else _audit_model(row)
            )(session.get(_AuditEventRow, event_id)),
        )

    def list_events(
        self,
        import_batch_id: str | None = None,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> tuple[AuditEvent, ...]:
        session = self._require_session()
        statement = select(_AuditEventRow).order_by(_AuditEventRow.sequence)
        if import_batch_id is not None:
            statement = statement.where(
                _AuditEventRow.import_batch_id == import_batch_id
            )
        if entity_type is not None:
            statement = statement.where(_AuditEventRow.entity_type == entity_type)
        if entity_id is not None:
            statement = statement.where(_AuditEventRow.entity_id == entity_id)
        return _safe_read(
            "audit event",
            lambda: tuple(
                _audit_model(row)
                for row in session.execute(statement).scalars().all()
            ),
        )

    def list_by_batch(self, batch_id: str) -> tuple[AuditEvent, ...]:
        """Return audit history correlated with one import batch."""

        return self.list_events(batch_id)


__all__ = [
    "AuditRepository",
    "CorruptStoredDataError",
    "DuplicateRecordError",
    "ForeignKeyViolationError",
    "ImportBatchRepository",
    "ProjectRepository",
    "RepositoryError",
    "SourceArtifactRepository",
    "StorageIntegrityError",
    "StorageWriteError",
]
