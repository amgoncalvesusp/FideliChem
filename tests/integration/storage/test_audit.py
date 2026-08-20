from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fidelichem.domain.models import AuditEvent, ImportBatch, Project
from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.services import StorageService
from fidelichem.storage.session import UnitOfWork

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def _project() -> Project:
    return Project(name="Audit", created_at=NOW, updated_at=NOW)


def _batch(project: Project) -> ImportBatch:
    return ImportBatch(
        project_id=project.id,
        adapter_id="adapter",
        adapter_version="1.0",
        started_at=NOW,
        source_root="inputs",
    )


def _seed_project(migrated_engine) -> Project:
    project = _project()
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
    return project


def test_audit_sequences_are_strictly_increasing_after_reopen(
    migrated_engine, database_path
) -> None:
    service = StorageService(migrated_engine)
    project = _seed_project(migrated_engine)
    batch = service.create_import_batch(_batch(project))
    service.complete_import_batch(batch.id)
    service.rollback_import_batch(batch.id, reason="audit test")

    migrated_engine.dispose()
    reopened_engine = create_sqlite_engine(database_path)
    try:
        with UnitOfWork(reopened_engine) as uow:
            events = uow.audit_events.list_events()
            sequences = [event.sequence for event in events]
            assert all(sequence is not None for sequence in sequences)
            assert sequences == sorted(sequences)
            assert len(set(sequences)) == len(sequences)
            assert all(
                events[index].id != str(events[index].sequence)
                for index in range(len(events))
            )
    finally:
        reopened_engine.dispose()


def test_audit_event_round_trip_preserves_null_and_empty_values(
    migrated_engine,
) -> None:
    project = _seed_project(migrated_engine)
    batch = _batch(project)
    with UnitOfWork(migrated_engine) as uow:
        uow.import_batches.add(batch)
        event = uow.audit_events.add(
            AuditEvent(
                timestamp=NOW,
                action="test.values",
                entity_type="import_batch",
                entity_id=batch.id,
                import_batch_id=batch.id,
                old_value_json="null",
                new_value_json='{"empty":"","enabled":false,"count":0}',
                source="test",
                actor_id=None,
            )
        )

    with UnitOfWork(migrated_engine) as uow:
        restored = uow.audit_events.get(event.id)
        assert restored is not None
        assert restored.old_value_json == "null"
        assert restored.new_value_json == '{"count":0,"empty":"","enabled":false}'
        assert restored.actor_id is None


def test_failed_service_transaction_leaves_no_new_audit_event(migrated_engine) -> None:
    service = StorageService(migrated_engine)
    project = _seed_project(migrated_engine)
    batch = service.create_import_batch(_batch(project))

    def failpoint(stage: str) -> None:
        if stage == "after_audit":
            raise RuntimeError("abort")

    with pytest.raises(RuntimeError, match="abort"):
        service.fail_import_batch(batch.id, failpoint=failpoint)

    with UnitOfWork(migrated_engine) as uow:
        events = uow.audit_events.list_by_batch(batch.id)
        assert len(events) == 1
        assert events[0].action == "import.created"
