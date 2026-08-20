from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from fidelichem.domain.models import (
    ActorKind,
    AuditEvent,
    ImportBatch,
    ImportStatus,
    Project,
    SourceArtifact,
)

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
HASH = "a" * 64


def identifier() -> str:
    return str(uuid4())


def test_project_is_frozen_and_forbids_extra_fields() -> None:
    project = Project(
        id=identifier(),
        name="Demo",
        created_at=NOW,
        updated_at=NOW,
        schema_version=1,
    )

    with pytest.raises(ValidationError):
        project.name = "Changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Project(
            id=identifier(),
            name="Demo",
            created_at=NOW,
            updated_at=NOW,
            schema_version=1,
            unexpected=True,
        )


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_project_rejects_blank_names(name: str) -> None:
    with pytest.raises(ValidationError, match="name"):
        Project(
            id=identifier(),
            name=name,
            created_at=NOW,
            updated_at=NOW,
            schema_version=1,
        )


def test_timestamps_are_aware_and_normalized_to_utc() -> None:
    offset = NOW.replace(tzinfo=timezone(timedelta(hours=-3)))
    project = Project(
        id=identifier(),
        name="Demo",
        created_at=offset,
        updated_at=NOW,
        schema_version=1,
    )

    assert project.created_at.tzinfo is UTC
    assert project.created_at == NOW + timedelta(hours=3)


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        Project(
            id=identifier(),
            name="Demo",
            created_at=NOW.replace(tzinfo=None),
            updated_at=NOW,
            schema_version=1,
        )


def test_import_batch_validates_status_counts_hash_and_preserves_nulls() -> None:
    batch = ImportBatch(
        id=identifier(),
        project_id=identifier(),
        adapter_id="generic-table",
        adapter_version="1.0",
        started_at=NOW,
        source_root="C:/inputs",
        file_count=0,
        input_hash=None,
        warnings=(),
        status=ImportStatus.IN_PROGRESS,
    )

    assert batch.status is ImportStatus.IN_PROGRESS
    assert batch.file_count == 0
    assert batch.input_hash is None
    assert batch.completed_at is None
    assert batch.warnings == ()

    with pytest.raises(ValidationError):
        ImportBatch(
            project_id=identifier(),
            adapter_id="adapter",
            adapter_version="1",
            started_at=NOW,
            source_root="inputs",
            file_count=-1,
        )
    with pytest.raises(ValidationError, match="sha256"):
        ImportBatch(
            project_id=identifier(),
            adapter_id="adapter",
            adapter_version="1",
            started_at=NOW,
            source_root="inputs",
            input_hash="A" * 64,
        )


def test_import_status_is_a_closed_string_enum() -> None:
    assert {status.value for status in ImportStatus} == {
        "in_progress",
        "completed",
        "failed",
        "rolled_back",
    }
    with pytest.raises(ValidationError):
        ImportBatch(
            project_id=identifier(),
            adapter_id="adapter",
            adapter_version="1",
            started_at=NOW,
            source_root="inputs",
            status="unknown",
        )


def test_source_artifact_rejects_unsafe_paths_hashes_and_sizes() -> None:
    artifact = SourceArtifact(
        import_batch_id=identifier(),
        path="C:/inputs/ligand.sdf",
        relative_path="ligands/ligand.sdf",
        sha256=HASH,
        file_type="sdf",
        size_bytes=0,
        mtime=NOW,
    )
    assert artifact.relative_path == "ligands/ligand.sdf"
    assert artifact.size_bytes == 0

    for path in (
        "/absolute/file",
        "../outside",
        "nested/../../outside",
        "C:/file",
        "C:\\file",
        "bad\x00name",
    ):
        with pytest.raises(ValidationError, match="relative_path"):
            SourceArtifact(
                import_batch_id=identifier(),
                path="source",
                relative_path=path,
                sha256=HASH,
                file_type="txt",
                size_bytes=1,
                mtime=NOW,
            )
    for digest in ("A" * 64, "a" * 63, "g" * 64):
        with pytest.raises(ValidationError, match="sha256"):
            SourceArtifact(
                import_batch_id=identifier(),
                path="source",
                relative_path="file.txt",
                sha256=digest,
                file_type="txt",
                size_bytes=1,
                mtime=NOW,
            )
    with pytest.raises(ValidationError):
        SourceArtifact(
            import_batch_id=identifier(),
            path="source",
            relative_path="file.txt",
            sha256=HASH,
            file_type="txt",
            size_bytes=-1,
            mtime=NOW,
        )


def test_public_ids_are_opaque_uuid4_values() -> None:
    project = Project(name="Demo", created_at=NOW, updated_at=NOW, schema_version=1)
    parsed = UUID(project.id)
    assert parsed.version == 4
    assert isinstance(project.id, str)


def test_audit_event_preserves_null_zero_false_and_empty_json_strings() -> None:
    event = AuditEvent(
        timestamp=NOW,
        action="import.completed",
        entity_type="import_batch",
        entity_id=identifier(),
        import_batch_id=None,
        old_values="null",
        new_values='{"count":0,"enabled":false,"label":""}',
        source="test",
        actor_kind=ActorKind.SYSTEM,
        actor_id=None,
        sequence=0,
    )

    assert event.import_batch_id is None
    assert event.old_values == "null"
    assert event.new_values == '{"count":0,"enabled":false,"label":""}'
    assert event.sequence == 0
    assert event.actor_id is None
