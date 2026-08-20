from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from fidelichem.domain.models import (
    ActorKind,
    AuditEvent,
    ImportBatch,
    ImportStatus,
    Project,
    SourceArtifact,
)
from fidelichem.storage.repositories import (
    DuplicateRecordError,
    ForeignKeyViolationError,
    ProjectRepository,
)
from fidelichem.storage.session import UnitOfWork, create_session_factory

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
HASH = "a" * 64


def _project(name: str = "Project") -> Project:
    return Project(name=name, created_at=NOW, updated_at=NOW, description=None)


def _batch(project: Project, *, source_root: str = "inputs") -> ImportBatch:
    return ImportBatch(
        project_id=project.id,
        adapter_id="generic-table",
        adapter_version="1.0",
        started_at=NOW,
        source_root=source_root,
        file_count=0,
        input_hash=None,
        warnings=(),
        status=ImportStatus.IN_PROGRESS,
    )


def _artifact(
    batch: ImportBatch, relative_path: str = "ligands/input.sdf"
) -> SourceArtifact:
    return SourceArtifact(
        import_batch_id=batch.id,
        path="C:/inputs/input.sdf",
        relative_path=relative_path,
        sha256=HASH,
        file_type="sdf",
        size_bytes=0,
        mtime=NOW,
    )


def _event(batch: ImportBatch | None = None) -> AuditEvent:
    return AuditEvent(
        timestamp=NOW,
        action="import.started",
        entity_type="import_batch",
        entity_id=batch.id if batch else "entity-1",
        import_batch_id=batch.id if batch else None,
        old_value_json=None,
        new_value_json='{"count":0,"enabled":false,"label":""}',
        source="test",
        actor_kind=ActorKind.SYSTEM,
        actor_id=None,
    )


def test_repositories_round_trip_all_entities_after_reopen(
    migrated_engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    project = _project()
    batch = _batch(project)
    artifact = _artifact(batch)
    with UnitOfWork(factory) as uow:
        stored_project = uow.projects.add(project)
        stored_batch = uow.import_batches.add(batch)
        stored_artifact = uow.source_artifacts.add(artifact)
        stored_event = uow.audit_events.add(_event(batch))

        assert stored_project == project
        assert stored_batch == batch
        assert stored_artifact == artifact
        assert stored_event.sequence is not None
        assert stored_event.new_value_json == '{"count":0,"enabled":false,"label":""}'

    with UnitOfWork(factory) as uow:
        assert uow.projects.get(project.id) == project
        assert uow.import_batches.get(batch.id) == batch
        assert uow.source_artifacts.get(artifact.id) == artifact
        assert uow.source_artifacts.list_by_batch(batch.id) == (artifact,)
        events = uow.audit_events.list_events(import_batch_id=batch.id)
        assert len(events) == 1
        assert events[0].id == stored_event.id
        assert uow.audit_events.get(stored_event.id) == stored_event


def test_reads_return_none_for_missing_records(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    with UnitOfWork(factory) as uow:
        assert uow.projects.get() is None
        assert uow.projects.get("00000000-0000-4000-8000-000000000000") is None
        assert uow.import_batches.get("00000000-0000-4000-8000-000000000000") is None
        assert uow.source_artifacts.get("00000000-0000-4000-8000-000000000000") is None
        assert uow.audit_events.get("00000000-0000-4000-8000-000000000000") is None


def test_repositories_use_caller_owned_session_without_commit(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    project = _project()
    with factory() as session:
        ProjectRepository(session).add(project)
        with migrated_engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM project")).scalar_one()
                == 0
            )
        session.commit()
    with factory() as session:
        assert ProjectRepository(session).get(project.id) == project


def test_duplicate_ids_and_second_project_are_typed_errors(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    project = _project()
    with UnitOfWork(factory) as uow:
        uow.projects.add(project)
    duplicate = _project("Other").model_copy(update={"id": project.id})
    with pytest.raises(DuplicateRecordError), UnitOfWork(factory) as uow:
        uow.projects.add(duplicate)
    with pytest.raises(DuplicateRecordError), UnitOfWork(factory) as uow:
        uow.projects.add(_project("Second"))


def test_duplicate_relative_path_is_a_typed_error(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    project = _project()
    batch = _batch(project)
    artifact = _artifact(batch)
    with UnitOfWork(factory) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.source_artifacts.add(artifact)
    with pytest.raises(DuplicateRecordError), UnitOfWork(factory) as uow:
        uow.source_artifacts.add(_artifact(batch))


def test_foreign_key_failures_do_not_expose_sql(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    orphan = _batch(_project()).model_copy()
    with pytest.raises(ForeignKeyViolationError) as error, UnitOfWork(factory) as uow:
        uow.import_batches.add(orphan)
    assert "FOREIGN KEY" not in str(error.value).upper()
    assert "import batch" in str(error.value)


def test_invalid_caller_owned_session_does_not_hide_integrity_error(
    migrated_engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    project = _project()
    with factory() as session:
        repository = ProjectRepository(session)
        repository.add(project)
        session.commit()
        with pytest.raises(DuplicateRecordError):
            repository.add(project)
        session.rollback()


def test_list_events_can_filter_entity_and_batch(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    project = _project()
    batch = _batch(project)
    with UnitOfWork(factory) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        first = uow.audit_events.add(_event(batch))
        second = uow.audit_events.add(
            _event(batch).model_copy(
                update={
                    "action": "import.completed",
                    "entity_type": "project",
                    "entity_id": project.id,
                }
            )
        )
    with UnitOfWork(factory) as uow:
        assert [item.id for item in uow.audit_events.list_events()] == [
            first.id,
            second.id,
        ]
        assert uow.audit_events.list_events(entity_type="project")[0].id == second.id


def test_session_factory_accepts_migrated_engine(migrated_engine) -> None:
    # The storage engine owns SQLite connection invariants; callers provide it
    # to the factory without depending on SQLAlchemy's sessionmaker details.
    factory = create_session_factory(migrated_engine)
    assert factory is not None
