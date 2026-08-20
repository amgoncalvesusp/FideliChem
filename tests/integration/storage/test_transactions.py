from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from fidelichem.domain.models import ImportBatch, Project
from fidelichem.storage.repositories import (
    ForeignKeyViolationError,
    ProjectRepository,
)
from fidelichem.storage.session import UnitOfWork, create_session_factory

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
