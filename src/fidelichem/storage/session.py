"""Session construction and transaction boundaries for storage operations."""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING, Literal

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from .repositories import (
        AuditRepository,
        ImportBatchRepository,
        ProjectRepository,
        SourceArtifactRepository,
    )

type SessionFactory = sessionmaker[Session]


class StorageError(RuntimeError):
    """Base class for safe public storage failures."""


class UnitOfWorkError(StorageError):
    """The unit-of-work lifecycle was used incorrectly."""


def create_session_factory(engine: Engine) -> SessionFactory:
    """Build a session factory bound to *engine*.

    ``expire_on_commit=False`` keeps domain values that were read before the
    boundary usable after the unit of work closes.  Repositories still map
    every row to a fresh immutable model before returning it.
    """

    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


class UnitOfWork:
    """Own exactly one SQLAlchemy session and transaction per context.

    A unit of work is intentionally single-use.  Reusing it would make it too
    easy to accidentally share a session between independent operations or
    threads.
    """

    def __init__(
        self,
        session_factory: Engine | SessionFactory | Callable[[], Session],
    ):
        self._session_factory = (
            create_session_factory(session_factory)
            if isinstance(session_factory, Engine)
            else session_factory
        )
        self._session: Session | None = None
        self._used = False

    if TYPE_CHECKING:
        projects: ProjectRepository
        import_batches: ImportBatchRepository
        source_artifacts: SourceArtifactRepository
        audit_events: AuditRepository

    @property
    def session(self) -> Session:
        if self._session is None:
            raise UnitOfWorkError("unit of work is not active")
        return self._session

    def __enter__(self) -> UnitOfWork:
        if self._used:
            raise UnitOfWorkError("unit of work cannot be reused")
        self._used = True
        try:
            self._session = self._session_factory()
            self._session.begin()
            self._install_repositories()
        except BaseException:
            if self._session is not None:
                self._session.rollback()
                self._session.close()
                self._session = None
            raise
        return self

    def _install_repositories(self) -> None:
        # Imported lazily to avoid a module cycle: repositories use the safe
        # StorageError types defined here.
        from .repositories import (
            AuditRepository,
            ImportBatchRepository,
            ProjectRepository,
            SourceArtifactRepository,
        )

        session = self.session
        self.projects = ProjectRepository(session)
        self.import_batches = ImportBatchRepository(session)
        self.source_artifacts = SourceArtifactRepository(session)
        self.audit_events = AuditRepository(session)
        # Singular aliases make the boundary convenient without hiding the
        # entity-specific repository classes.
        self.project = self.projects
        self.import_batch = self.import_batches
        self.source_artifact = self.source_artifacts
        self.audit = self.audit_events
        self.project_repository = self.projects
        self.import_batch_repository = self.import_batches
        self.source_artifact_repository = self.source_artifacts
        self.audit_repository = self.audit_events

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del traceback
        session = self._session
        if session is None:
            return False
        try:
            if exc_type is None:
                try:
                    session.commit()
                except BaseException:
                    session.rollback()
                    raise
            else:
                session.rollback()
        finally:
            session.close()
            self._session = None
        del exc_value
        return False


__all__ = [
    "SessionFactory",
    "StorageError",
    "UnitOfWork",
    "UnitOfWorkError",
    "create_session_factory",
]
