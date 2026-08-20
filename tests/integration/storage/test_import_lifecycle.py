from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fidelichem.domain.errors import InvalidStatusTransitionError
from fidelichem.domain.models import ImportBatch, ImportStatus, Project, SourceArtifact
from fidelichem.storage.services import StorageService
from fidelichem.storage.session import UnitOfWork

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
HASH = "b" * 64


def _project() -> Project:
    return Project(name="Lifecycle", created_at=NOW, updated_at=NOW)


def _batch(project: Project) -> ImportBatch:
    return ImportBatch(
        project_id=project.id,
        adapter_id="adapter",
        adapter_version="1.0",
        started_at=NOW,
        source_root="inputs",
        warnings=("first", "second"),
    )


def _artifact(batch: ImportBatch) -> SourceArtifact:
    return SourceArtifact(
        import_batch_id=batch.id,
        path="C:/inputs/ligand.sdf",
        relative_path="ligand.sdf",
        sha256=HASH,
        file_type="sdf",
        size_bytes=12,
        mtime=NOW,
    )


def _seed_project(migrated_engine) -> Project:
    project = _project()
    with UnitOfWork(migrated_engine) as uow:
        uow.projects.add(project)
    return project


def _create_batch(migrated_engine) -> tuple[StorageService, Project, ImportBatch]:
    service = StorageService(migrated_engine)
    project = _seed_project(migrated_engine)
    batch = service.create_import_batch(_batch(project))
    return service, project, batch


def test_create_and_complete_import_batch_are_audited(migrated_engine) -> None:
    service, project, batch = _create_batch(migrated_engine)
    completed_at = NOW + timedelta(hours=1)
    completed = service.complete_import_batch(batch.id, completed_at=completed_at)

    assert completed.status is ImportStatus.COMPLETED
    assert completed.completed_at == completed_at
    assert completed.warnings == ("first", "second")
    with UnitOfWork(migrated_engine) as uow:
        events = uow.audit_events.list_by_batch(batch.id)
        assert [event.action for event in events] == [
            "import.created",
            "import.completed",
        ]
        assert uow.projects.get(project.id) == project


def test_fail_import_batch_records_completion_timestamp(migrated_engine) -> None:
    service, _, batch = _create_batch(migrated_engine)
    failed_at = NOW + timedelta(minutes=10)
    failed = service.fail_import_batch(batch.id, completed_at=failed_at)

    assert failed.status is ImportStatus.FAILED
    assert failed.completed_at == failed_at
    with UnitOfWork(migrated_engine) as uow:
        assert uow.audit_events.list_by_batch(batch.id)[-1].action == "import.failed"


@pytest.mark.parametrize(
    "terminal_method", ["complete_import_batch", "fail_import_batch"]
)
def test_terminal_transition_cannot_be_repeated(
    migrated_engine, terminal_method: str
) -> None:
    service, _, batch = _create_batch(migrated_engine)
    getattr(service, terminal_method)(batch.id)
    with pytest.raises(InvalidStatusTransitionError):
        getattr(service, terminal_method)(batch.id)


def test_rollback_requires_terminal_batch_and_is_idempotent(migrated_engine) -> None:
    service, _, batch = _create_batch(migrated_engine)
    artifact = _artifact(batch)
    with UnitOfWork(migrated_engine) as uow:
        uow.source_artifacts.add(artifact)

    with pytest.raises(InvalidStatusTransitionError):
        service.rollback_import_batch(batch.id, reason="too early")

    service.complete_import_batch(batch.id)
    rolled_back = service.rollback_import_batch(batch.id, reason="withdrawn")
    repeated = service.rollback_import_batch(batch.id, reason="different")

    assert rolled_back.status is ImportStatus.ROLLED_BACK
    assert rolled_back.rollback_reason == "withdrawn"
    assert repeated == rolled_back
    with UnitOfWork(migrated_engine) as uow:
        assert uow.source_artifacts.list_by_batch(batch.id) == (artifact,)
        rollback_events = [
            event
            for event in uow.audit_events.list_by_batch(batch.id)
            if event.action == "import.rolled_back"
        ]
        assert len(rollback_events) == 1


def test_failpoint_before_audit_rolls_back_lifecycle_and_audit(migrated_engine) -> None:
    service, _, batch = _create_batch(migrated_engine)

    def failpoint(stage: str) -> None:
        if stage == "before_audit":
            raise RuntimeError("failpoint")

    with pytest.raises(RuntimeError, match="failpoint"):
        service.complete_import_batch(batch.id, failpoint=failpoint)

    with UnitOfWork(migrated_engine) as uow:
        unchanged = uow.import_batches.get(batch.id)
        assert unchanged == batch
        assert [event.action for event in uow.audit_events.list_by_batch(batch.id)] == [
            "import.created"
        ]


def test_failpoint_after_audit_rolls_back_false_success_event(migrated_engine) -> None:
    service, _, batch = _create_batch(migrated_engine)

    def failpoint(stage: str) -> None:
        if stage == "after_audit":
            raise RuntimeError("after audit")

    with pytest.raises(RuntimeError, match="after audit"):
        service.complete_import_batch(batch.id, failpoint=failpoint)

    with UnitOfWork(migrated_engine) as uow:
        assert uow.import_batches.get(batch.id) == batch
        assert len(uow.audit_events.list_by_batch(batch.id)) == 1
