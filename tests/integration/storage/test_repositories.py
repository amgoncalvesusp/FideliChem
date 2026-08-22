from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from fidelichem.domain.models import (
    ActorKind,
    AuditEvent,
    ImportBatch,
    ImportStatus,
    Project,
    SourceArtifact,
)
from fidelichem.storage.repositories import (
    CorruptStoredDataError,
    DuplicateRecordError,
    ForeignKeyViolationError,
    InvalidProjectUpdateError,
    OptimisticConcurrencyError,
    ProjectRepository,
    StorageReadError,
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


def test_project_repository_updates_metadata_and_preserves_immutable_fields(
    migrated_engine,
) -> None:
    project = _project()
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)

    updated = project.model_copy(
        update={
            "name": "Renamed",
            "description": "Updated metadata",
            "updated_at": NOW + timedelta(minutes=1),
        }
    )
    with UnitOfWork(migrated_engine) as uow:
        stored = uow.projects.update(
            updated,
            expected_updated_at=project.updated_at,
        )

    assert stored.name == "Renamed"
    assert stored.description == "Updated metadata"
    assert stored.id == project.id
    assert stored.created_at == project.created_at
    assert stored.schema_version == project.schema_version

    with UnitOfWork(migrated_engine) as uow:
        assert uow.projects.update(stored) == stored


def test_project_repository_rejects_stale_metadata_update(migrated_engine) -> None:
    project = _project()
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        current = uow.projects.update(
            project.model_copy(
                update={
                    "name": "First",
                    "updated_at": NOW + timedelta(minutes=1),
                }
            )
        )
        with pytest.raises(OptimisticConcurrencyError):
            uow.projects.update(
                project.model_copy(
                    update={
                        "name": "Stale",
                        "updated_at": NOW + timedelta(minutes=2),
                    }
                ),
                expected_updated_at=project.updated_at,
            )
        assert uow.projects.get(project.id) == current


def test_project_repository_rejects_unvalidated_immutable_metadata_changes(
    migrated_engine,
) -> None:
    project = _project()
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        invalid = project.model_copy(update={"name": "Changed", "schema_version": True})
        with pytest.raises(InvalidProjectUpdateError):
            uow.projects.update(invalid)


def test_sqlalchemy_read_fault_is_safe_and_distinct_from_corruption(
    migrated_engine,
) -> None:
    class FailingReadSession(Session):
        def execute(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise OperationalError("SELECT secret/path", {}, RuntimeError("secret"))

    session = FailingReadSession(bind=migrated_engine)
    try:
        with pytest.raises(StorageReadError) as error:
            ProjectRepository(session).get()
        assert "SELECT" not in str(error.value).upper()
        assert "secret" not in str(error.value).lower()
        assert not isinstance(error.value, CorruptStoredDataError)
    finally:
        session.close()


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


def test_corrupt_project_row_is_a_safe_domain_error(migrated_engine) -> None:
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO project "
                "(id,name,description,created_at,updated_at,schema_version) "
                "VALUES (:id,:name,:description,:created_at,:updated_at,:version)"
            ),
            {
                "id": "not-a-uuid",
                "name": "Project",
                "description": None,
                "created_at": "not-a-timestamp",
                "updated_at": "not-a-timestamp",
                "version": 1,
            },
        )
        connection.commit()

    with (
        pytest.raises(CorruptStoredDataError, match="stored project"),
        UnitOfWork(migrated_engine) as uow,
    ):
        uow.projects.get()


def test_corrupt_batch_warnings_are_a_safe_domain_error(migrated_engine) -> None:
    project = _project()
    batch = _batch(project)
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)

    with migrated_engine.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO import_batch "
                "(id,project_id,adapter_id,adapter_version,started_at,status,"
                "source_root,file_count,input_hash,warnings_json) "
                "VALUES (:id,:project_id,:adapter_id,:adapter_version,:started_at,"
                ":status,:source_root,:file_count,:input_hash,:warnings_json)"
            ),
            {
                "id": batch.id,
                "project_id": project.id,
                "adapter_id": batch.adapter_id,
                "adapter_version": batch.adapter_version,
                "started_at": NOW.isoformat().replace("+00:00", "Z"),
                "status": batch.status.value,
                "source_root": batch.source_root,
                "file_count": 0,
                "input_hash": None,
                "warnings_json": "null",
            },
        )
        connection.commit()

    with (
        pytest.raises(CorruptStoredDataError, match="stored import batch"),
        UnitOfWork(migrated_engine) as uow,
    ):
        uow.import_batches.get(batch.id)


def test_corrupt_artifact_id_is_a_safe_domain_error(migrated_engine) -> None:
    project = _project()
    batch = _batch(project)
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)

    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO source_artifact "
                "(id,import_batch_id,path,relative_path,sha256,file_type,size_bytes,"
                "mtime) "
                "VALUES (:id,:batch,:path,:relative_path,:sha256,:file_type,:size,"
                ":mtime)"
            ),
            {
                "id": "not-a-uuid",
                "batch": batch.id,
                "path": "input.sdf",
                "relative_path": "input.sdf",
                "sha256": "bad",
                "file_type": "sdf",
                "size": 0,
                "mtime": NOW.isoformat().replace("+00:00", "Z"),
            },
        )
        connection.commit()

    with (
        pytest.raises(CorruptStoredDataError, match="stored source artifact"),
        UnitOfWork(migrated_engine) as uow,
    ):
        uow.source_artifacts.get("not-a-uuid")


def test_corrupt_audit_actor_is_a_safe_domain_error(migrated_engine) -> None:
    with migrated_engine.connect() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints=ON"))
        connection.execute(
            text(
                "INSERT INTO audit_event "
                "(id,sequence,timestamp,action,entity_type,entity_id,source,"
                "actor_kind) "
                "VALUES (:id,NULL,:timestamp,:action,:entity_type,:entity_id,"
                ":source,:actor)"
            ),
            {
                "id": "not-a-uuid",
                "timestamp": NOW.isoformat().replace("+00:00", "Z"),
                "action": "test",
                "entity_type": "project",
                "entity_id": "not-a-uuid",
                "source": "test",
                "actor": "robot",
            },
        )
        connection.commit()

    with (
        pytest.raises(CorruptStoredDataError, match="stored audit event"),
        UnitOfWork(migrated_engine) as uow,
    ):
        uow.audit_events.get("not-a-uuid")
