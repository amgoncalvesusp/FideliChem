"""Session construction and transaction boundaries for storage operations."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from types import TracebackType
from typing import TYPE_CHECKING, Literal, Protocol

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from .chemistry_repositories import (
        AliasRepository,
        CompoundRepository,
        IdentityResolutionRepository,
        MolecularStateRepository,
    )
    from .evidence_repositories import EvidenceRepository
    from .repositories import (
        AuditRepository,
        ImportBatchRepository,
        ProjectRepository,
        SourceArtifactRepository,
    )


class _RepositoryLifecycle(Protocol):
    def _deactivate(self) -> None: ...


type SessionFactory = sessionmaker[Session]
UNIT_OF_WORK_FLAG = "_fidelichem_unit_of_work"
TRANSACTION_FAILED_FLAG = "_fidelichem_transaction_failed"
UNIT_OF_WORK_FAILED_FLAG = "_fidelichem_unit_of_work_failed"


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
        self._repositories: tuple[_RepositoryLifecycle, ...] = ()

    if TYPE_CHECKING:
        compounds: CompoundRepository
        molecular_states: MolecularStateRepository
        aliases: AliasRepository
        identity_resolutions: IdentityResolutionRepository
        projects: ProjectRepository
        import_batches: ImportBatchRepository
        source_artifacts: SourceArtifactRepository
        audit_events: AuditRepository
        evidence: EvidenceRepository

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
            self._session.info[UNIT_OF_WORK_FLAG] = True
            self._session.begin()
            self._install_repositories()
        except SQLAlchemyError:
            if self._session is not None:
                self._rollback_quietly(self._session)
                self._close_quietly(self._session)
                self._session = None
            raise UnitOfWorkError("could not begin storage transaction") from None
        except BaseException:
            if self._session is not None:
                self._rollback_quietly(self._session)
                self._close_quietly(self._session)
                self._session = None
            raise
        return self

    def _install_repositories(self) -> None:
        # Imported lazily to avoid a module cycle: repositories use the safe
        # StorageError types defined here.
        from .chemistry_repositories import (
            AliasRepository,
            CompoundRepository,
            IdentityResolutionRepository,
            MolecularStateRepository,
        )
        from .evidence_repositories import EvidenceRepository
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
        self.compounds = CompoundRepository(session)
        self.molecular_states = MolecularStateRepository(session)
        self.aliases = AliasRepository(session)
        self.identity_resolutions = IdentityResolutionRepository(session)
        self.evidence = EvidenceRepository(session)
        self._repositories = (
            self.projects,
            self.import_batches,
            self.source_artifacts,
            self.audit_events,
            self.compounds,
            self.molecular_states,
            self.aliases,
            self.identity_resolutions,
            self.evidence,
        )

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
            if exc_type is not None:
                self._rollback_quietly(session)
                return False
            if session.info.get(UNIT_OF_WORK_FAILED_FLAG, False):
                self._rollback_quietly(session)
                raise UnitOfWorkError("storage transaction failed and was rolled back")
            try:
                session.commit()
            except SQLAlchemyError:
                self._rollback_quietly(session)
                raise UnitOfWorkError("could not commit storage transaction") from None
        finally:
            for repository in self._repositories:
                repository._deactivate()
            session.info.pop(UNIT_OF_WORK_FLAG, None)
            self._close_quietly(session)
            self._session = None
        del exc_value
        return False

    @staticmethod
    def _rollback_quietly(session: Session) -> None:
        with suppress(BaseException):
            session.rollback()

    @staticmethod
    def _close_quietly(session: Session) -> None:
        with suppress(BaseException):
            session.close()


__all__ = [
    "SessionFactory",
    "StorageError",
    "TRANSACTION_FAILED_FLAG",
    "UNIT_OF_WORK_FAILED_FLAG",
    "UNIT_OF_WORK_FLAG",
    "UnitOfWork",
    "UnitOfWorkError",
    "create_session_factory",
]
