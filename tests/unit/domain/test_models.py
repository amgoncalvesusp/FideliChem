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


@pytest.mark.parametrize("value", [True, False])
def test_project_schema_version_rejects_boolean_numbers(value: bool) -> None:
    with pytest.raises(ValidationError, match="schema_version"):
        Project(
            name="Demo",
            created_at=NOW,
            updated_at=NOW,
            schema_version=value,
        )


@pytest.mark.parametrize("value", [True, False])
def test_import_batch_file_count_rejects_boolean_numbers(value: bool) -> None:
    with pytest.raises(ValidationError, match="file_count"):
        ImportBatch(
            project_id=identifier(),
            adapter_id="adapter",
            adapter_version="1",
            started_at=NOW,
            source_root="inputs",
            file_count=value,
        )


@pytest.mark.parametrize("value", [True, False])
def test_source_artifact_size_bytes_rejects_boolean_numbers(value: bool) -> None:
    with pytest.raises(ValidationError, match="size_bytes"):
        SourceArtifact(
            import_batch_id=identifier(),
            path="source/file.sdf",
            relative_path="file.sdf",
            sha256=HASH,
            file_type="sdf",
            size_bytes=value,
            mtime=NOW,
        )


@pytest.mark.parametrize("value", [True, False])
def test_audit_sequence_rejects_boolean_numbers(value: bool) -> None:
    with pytest.raises(ValidationError, match="sequence"):
        AuditEvent(
            timestamp=NOW,
            action="created",
            entity_type="project",
            entity_id=identifier(),
            source="test",
            sequence=value,
        )


@pytest.mark.parametrize(
    ("model", "payload", "field"),
    [
        (
            Project,
            '{"name":"Demo","created_at":"2026-08-20T12:00:00Z",'
            '"updated_at":"2026-08-20T12:00:00Z","schema_version":true}',
            "schema_version",
        ),
        (
            ImportBatch,
            '{"project_id":"11111111-1111-4111-8111-111111111111",'
            '"adapter_id":"adapter","adapter_version":"1",'
            '"started_at":"2026-08-20T12:00:00Z","source_root":"inputs",'
            '"file_count":true}',
            "file_count",
        ),
        (
            SourceArtifact,
            '{"import_batch_id":"11111111-1111-4111-8111-111111111111",'
            '"path":"source/file.sdf","relative_path":"file.sdf",'
            '"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            '"file_type":"sdf","size_bytes":true,'
            '"mtime":"2026-08-20T12:00:00Z"}',
            "size_bytes",
        ),
        (
            AuditEvent,
            '{"timestamp":"2026-08-20T12:00:00Z","action":"created",'
            '"entity_type":"project",'
            '"entity_id":"11111111-1111-4111-8111-111111111111",'
            '"source":"test","sequence":true}',
            "sequence",
        ),
    ],
)
def test_numeric_fields_reject_boolean_json(
    model: type[object], payload: str, field: str
) -> None:
    with pytest.raises(ValidationError, match=field):
        model.model_validate_json(payload)  # type: ignore[attr-defined]


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
    assert artifact.mtime == NOW
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
        old_value_json="null",
        new_value_json='{"count":0,"enabled":false,"label":""}',
        source="test",
        actor_kind=ActorKind.SYSTEM,
        actor_id=None,
        sequence=0,
    )

    assert event.import_batch_id is None
    assert event.old_value_json == "null"
    assert event.new_value_json == '{"count":0,"enabled":false,"label":""}'
    assert event.sequence == 0
    assert event.actor_id is None


def test_source_artifact_round_trips_with_only_mtime_public_name() -> None:
    artifact = SourceArtifact(
        import_batch_id=identifier(),
        path="source/file.sdf",
        relative_path="file.sdf",
        sha256=HASH,
        file_type="sdf",
        size_bytes=0,
        mtime=NOW,
    )

    dumped = artifact.model_dump()
    assert "mtime" in dumped
    assert "modified_at" not in dumped
    assert SourceArtifact.model_validate(dumped) == artifact
    assert SourceArtifact.model_validate_json(artifact.model_dump_json()) == artifact
    assert "mtime" in SourceArtifact.model_json_schema()["properties"]
    assert "modified_at" not in SourceArtifact.model_json_schema()["properties"]


def test_audit_event_round_trips_with_singular_json_names() -> None:
    event = AuditEvent(
        timestamp=NOW,
        action="import.completed",
        entity_type="import_batch",
        entity_id=identifier(),
        old_value_json=None,
        new_value_json="null",
        source="test",
    )

    dumped = event.model_dump()
    assert "old_value_json" in dumped
    assert "new_value_json" in dumped
    assert "old_values" not in dumped
    assert "new_values" not in dumped
    assert AuditEvent.model_validate(dumped) == event
    assert AuditEvent.model_validate_json(event.model_dump_json()) == event
    properties = AuditEvent.model_json_schema()["properties"]
    assert "old_value_json" in properties
    assert "new_value_json" in properties
    assert "old_values" not in properties
    assert "new_values" not in properties


@pytest.mark.parametrize("field", ["modified_at"])
def test_source_artifact_rejects_legacy_public_names(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        SourceArtifact(
            import_batch_id=identifier(),
            path="source/file.sdf",
            relative_path="file.sdf",
            sha256=HASH,
            file_type="sdf",
            size_bytes=0,
            **{field: NOW},
        )


@pytest.mark.parametrize(
    "field", ["old_values", "new_values", "old_values_json", "new_values_json"]
)
def test_audit_event_rejects_legacy_public_names(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        AuditEvent(
            timestamp=NOW,
            action="import.completed",
            entity_type="import_batch",
            entity_id=identifier(),
            source="test",
            **{field: "null"},
        )
