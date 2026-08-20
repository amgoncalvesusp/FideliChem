from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from fidelichem.domain.models import ImportBatch, Project
from fidelichem.storage.repositories import (
    ForeignKeyViolationError,
    ImportBatchRepository,
    ProjectRepository,
)
from fidelichem.storage.session import (
    UnitOfWork,
    UnitOfWorkError,
    create_session_factory,
)

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def _project(name: str = "Project") -> Project:
    return Project(name=name, created_at=NOW, updated_at=NOW)


def _batch(project_id: str) -> ImportBatch:
    return ImportBatch(
        project_id=project_id,
        adapter_id="adapter",
        adapter_version="1",
        started_at=NOW,
        source_root="inputs",
    )


def test_uncommitted_data_is_hidden_and_successful_commit_is_reopened(
    migrated_engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    project = _project()
    with factory() as first, factory() as second:
        ProjectRepository(first).add(project)
        assert first.execute(text("SELECT count(*) FROM project")).scalar_one() == 1
        assert second.execute(text("SELECT count(*) FROM project")).scalar_one() == 0
        first.commit()
        assert second.execute(text("SELECT count(*) FROM project")).scalar_one() == 1

    with UnitOfWork(factory) as uow:
        assert uow.projects.get(project.id) == project


def test_exception_after_multiple_writes_rolls_back_everything(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    project = _project()
    batch = _batch(project.id)
    with pytest.raises(RuntimeError, match="failpoint"), UnitOfWork(factory) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        raise RuntimeError("failpoint")

    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM project")).scalar_one() == 0
        assert (
            session.execute(text("SELECT count(*) FROM import_batch")).scalar_one() == 0
        )


def test_foreign_key_failure_rolls_back_prior_writes(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    project = _project()
    with pytest.raises(ForeignKeyViolationError), UnitOfWork(factory) as uow:
        uow.projects.add(project)
        uow.import_batches.add(_batch("00000000-0000-4000-8000-000000000000"))

    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM project")).scalar_one() == 0


def test_unit_of_work_closes_and_cannot_be_reused(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    uow = UnitOfWork(factory)
    with uow:
        assert uow.session.is_active
    from fidelichem.storage.session import UnitOfWorkError

    with pytest.raises(UnitOfWorkError, match="reused"), uow:
        pass


def test_repositories_become_inactive_after_unit_of_work_exit(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    with UnitOfWork(factory) as uow:
        projects = uow.projects
        artifacts = uow.source_artifacts

    with pytest.raises(UnitOfWorkError, match="inactive"):
        projects.get()
    with pytest.raises(UnitOfWorkError, match="inactive"):
        projects.add(_project())
    with pytest.raises(UnitOfWorkError, match="inactive"):
        artifacts.list_by_batch("00000000-0000-4000-8000-000000000000")
    with pytest.raises(UnitOfWorkError, match="not active"):
        _ = uow.session


def test_unit_of_work_enter_sqlalchemy_failure_is_safe(migrated_engine) -> None:
    class FailingBeginSession(Session):
        def begin(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise SQLAlchemyError("secret connection details")

    factory = create_session_factory(migrated_engine)

    def failing_factory() -> Session:
        return FailingBeginSession(bind=factory.kw["bind"])

    with pytest.raises(UnitOfWorkError, match="begin storage"), UnitOfWork(
        failing_factory
    ):
        pass


def test_unit_of_work_enter_non_sqlalchemy_failure_is_preserved(
    migrated_engine,
) -> None:
    del migrated_engine

    def failing_factory() -> Session:
        raise RuntimeError("factory failure")

    with pytest.raises(RuntimeError, match="factory failure"), UnitOfWork(
        failing_factory
    ):
        pass


def test_unit_of_work_commit_sqlalchemy_failure_is_safe(migrated_engine) -> None:
    class FailingCommitSession(Session):
        def commit(self) -> None:
            raise SQLAlchemyError("secret commit details")

    factory = create_session_factory(migrated_engine)

    def failing_factory() -> Session:
        return FailingCommitSession(bind=factory.kw["bind"])

    with pytest.raises(UnitOfWorkError, match="commit storage"), UnitOfWork(
        failing_factory
    ):
        pass


def test_caught_flush_failure_fails_closed_and_uow_raises_on_exit(
    migrated_engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    project = _project()
    with pytest.raises(UnitOfWorkError, match="failed"), UnitOfWork(factory) as uow:
        uow.projects.add(project)
        with suppress(ForeignKeyViolationError):
            uow.import_batches.add(_batch("00000000-0000-4000-8000-000000000000"))
        with pytest.raises(UnitOfWorkError, match="failed"):
            uow.projects.get(project.id)

    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM project")).scalar_one() == 0
        assert (
            session.execute(text("SELECT count(*) FROM import_batch")).scalar_one() == 0
        )


def test_uncaught_flush_failure_preserves_typed_error_after_rollback(
    migrated_engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with pytest.raises(ForeignKeyViolationError), UnitOfWork(factory) as uow:
        uow.projects.add(_project())
        uow.import_batches.add(_batch("00000000-0000-4000-8000-000000000000"))

    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM project")).scalar_one() == 0


def test_unit_of_work_stays_failed_after_explicit_inner_rollback(
    migrated_engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with pytest.raises(UnitOfWorkError, match="failed"), UnitOfWork(factory) as uow:
        with suppress(ForeignKeyViolationError):
            uow.import_batches.add(
                _batch("00000000-0000-4000-8000-000000000000")
            )
        uow.session.rollback()
        with pytest.raises(UnitOfWorkError, match="failed"):
            uow.projects.get()


def test_caller_owned_repository_fails_closed_after_flush_failure(
    migrated_engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with factory() as session:
        repository = ProjectRepository(session)
        repository.add(_project())
        with pytest.raises(ForeignKeyViolationError):
            # The project repository's session is deliberately failed by a
            # repository using the same caller-owned transaction.
            from fidelichem.storage.repositories import ImportBatchRepository

            ImportBatchRepository(session).add(
                _batch("00000000-0000-4000-8000-000000000000")
            )
        with pytest.raises(UnitOfWorkError, match="failed"):
            repository.get()


def test_caller_owned_repository_recovers_after_explicit_rollback(
    migrated_engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with factory() as session:
        repository = ProjectRepository(session)
        repository.add(_project())
        with pytest.raises(ForeignKeyViolationError):
            ImportBatchRepository(session).add(
                _batch("00000000-0000-4000-8000-000000000000")
            )
        with pytest.raises(UnitOfWorkError, match="failed"):
            repository.get()

        session.rollback()
        recovered = ProjectRepository(session)
        assert recovered.get() is None
        recovered.add(_project("Recovered"))
        session.commit()
