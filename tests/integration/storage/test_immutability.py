from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from fidelichem.domain.models import AuditEvent, ImportBatch, Project, SourceArtifact
from fidelichem.storage.session import UnitOfWork

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
HASH = "a" * 64


def _project() -> Project:
    return Project(name="Project", created_at=NOW, updated_at=NOW)


def _batch(project: Project) -> ImportBatch:
    return ImportBatch(
        project_id=project.id,
        adapter_id="adapter",
        adapter_version="1.0",
        started_at=NOW,
        source_root="inputs",
    )


def _artifact(batch: ImportBatch) -> SourceArtifact:
    return SourceArtifact(
        import_batch_id=batch.id,
        path="C:/inputs/ligand.sdf",
        relative_path="ligand.sdf",
        sha256=HASH,
        file_type="sdf",
        size_bytes=10,
        mtime=NOW,
    )


def _audit(batch: ImportBatch) -> AuditEvent:
    return AuditEvent(
        timestamp=NOW,
        action="import.started",
        entity_type="import_batch",
        entity_id=batch.id,
        import_batch_id=batch.id,
        source="test",
    )


def _seed(migrated_engine) -> tuple[Project, ImportBatch, SourceArtifact, AuditEvent]:
    project = _project()
    batch = _batch(project)
    artifact = _artifact(batch)
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
        uow.import_batches.add(batch)
        uow.source_artifacts.add(artifact)
        audit = uow.audit_events.add(_audit(batch))
    return project, batch, artifact, audit


def _assert_direct_sql_rejected(connection, statement, parameters) -> None:
    with pytest.raises(IntegrityError):
        connection.execute(text(statement), parameters)
    connection.rollback()


def test_source_artifacts_reject_update_delete_and_replace(migrated_engine) -> None:
    _, batch, artifact, _ = _seed(migrated_engine)
    with migrated_engine.connect() as connection:
        _assert_direct_sql_rejected(
            connection,
            "UPDATE source_artifact SET path = :path WHERE id = :id",
            {"path": "changed", "id": artifact.id},
        )
        _assert_direct_sql_rejected(
            connection,
            "DELETE FROM source_artifact WHERE id = :id",
            {"id": artifact.id},
        )
        _assert_direct_sql_rejected(
            connection,
            "INSERT OR REPLACE INTO source_artifact "
            "(id,import_batch_id,path,relative_path,sha256,file_type,size_bytes,mtime) "
            "VALUES (:id,:batch,:path,:relative_path,:sha256,:file_type,:size,:mtime)",
            {
                "id": artifact.id,
                "batch": batch.id,
                "path": "replacement",
                "relative_path": artifact.relative_path,
                "sha256": HASH,
                "file_type": "sdf",
                "size": 99,
                "mtime": NOW.isoformat().replace("+00:00", "Z"),
            },
        )

    with UnitOfWork(migrated_engine) as uow:
        assert uow.source_artifacts.get(artifact.id) == artifact


def test_audit_events_reject_update_delete_and_replace(migrated_engine) -> None:
    _, batch, _, audit = _seed(migrated_engine)
    with migrated_engine.connect() as connection:
        _assert_direct_sql_rejected(
            connection,
            "UPDATE audit_event SET action = :action WHERE id = :id",
            {"action": "changed", "id": audit.id},
        )
        _assert_direct_sql_rejected(
            connection,
            "DELETE FROM audit_event WHERE id = :id",
            {"id": audit.id},
        )
        _assert_direct_sql_rejected(
            connection,
            "INSERT OR REPLACE INTO audit_event "
            "(id,timestamp,action,entity_type,entity_id,import_batch_id,source) "
            "VALUES (:id,:timestamp,:action,:entity_type,:entity_id,:batch,:source)",
            {
                "id": audit.id,
                "timestamp": NOW.isoformat().replace("+00:00", "Z"),
                "action": "replacement",
                "entity_type": "import_batch",
                "entity_id": batch.id,
                "batch": batch.id,
                "source": "test",
            },
        )

    with UnitOfWork(migrated_engine) as uow:
        assert uow.audit_events.get(audit.id) == audit


def test_import_batch_immutable_fields_reject_direct_update(migrated_engine) -> None:
    _, batch, _, _ = _seed(migrated_engine)
    with migrated_engine.connect() as connection:
        _assert_direct_sql_rejected(
            connection,
            "UPDATE import_batch SET adapter_id = :adapter WHERE id = :id",
            {"adapter": "changed", "id": batch.id},
        )
        connection.execute(
            text("UPDATE import_batch SET completed_at = :completed WHERE id = :id"),
            {
                "completed": NOW.isoformat().replace("+00:00", "Z"),
                "id": batch.id,
            },
        )
        connection.rollback()
