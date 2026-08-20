from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from fidelichem.domain.json import canonical_json_bytes
from fidelichem.domain.models import ImportBatch, ImportStatus, SourceArtifact
from fidelichem.projects import service as project_service
from fidelichem.projects.layout import ProjectPaths
from fidelichem.projects.service import (
    ProjectConflictError,
    ProjectManifestError,
    UnsafeManifestPathError,
    create_project,
    open_project,
)
from fidelichem.storage.repositories import StorageWriteError
from fidelichem.storage.runner import MigrationError
from fidelichem.storage.session import UnitOfWork

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
HASH = "c" * 64


def test_create_project_writes_exact_layout_and_canonical_manifest(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Demo"
    created = create_project(root, "Demonstração", description="Unicode")

    assert isinstance(created, ProjectPaths)
    assert created.root == root.resolve()
    assert created.manifest == root.resolve() / "project.json"
    assert created.database == root.resolve() / "project.fidelichem.sqlite"
    assert [path.name for path in created.directories] == [
        "artifacts",
        "cache",
        "exports",
        "logs",
    ]
    assert {path.name for path in root.iterdir()} == {
        "project.json",
        "project.fidelichem.sqlite",
        "artifacts",
        "cache",
        "exports",
        "logs",
    }
    raw = created.manifest.read_bytes()
    assert raw.decode("utf-8") == json.dumps(
        json.loads(raw),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    manifest = json.loads(raw)
    assert manifest == {
        "database": "project.fidelichem.sqlite",
        "name": "Demonstração",
        "project_id": created.project.id,
        "schema_version": 1,
    }
    assert created.project.description == "Unicode"


def test_reopen_preserves_project_id_and_supports_read_only_mode(
    tmp_path: Path,
) -> None:
    created = create_project(tmp_path / "Demo", "Demo")
    created.close()

    reopened = open_project(created.root)
    read_only = open_project(created.root, read_only=True)
    try:
        assert reopened.project.id == created.project.id
        assert reopened.project == created.project
        assert read_only.project == created.project
        assert read_only.read_only is True
    finally:
        reopened.close()
        read_only.close()


def test_unicode_project_name_round_trips_without_ascii_escaping(
    tmp_path: Path,
) -> None:
    created = create_project(tmp_path / "projeto", "μ-FideliChem — 项目")
    reopened = open_project(created.root)
    try:
        assert reopened.project.name == "μ-FideliChem — 项目"
    finally:
        reopened.close()


def test_conflicting_project_is_never_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "Demo"
    created = create_project(root, "Original")
    original_manifest = created.manifest.read_bytes()
    original_id = created.project.id
    created.close()

    with pytest.raises(ProjectConflictError):
        create_project(root, "Replacement")

    assert created.manifest.read_bytes() == original_manifest
    reopened = open_project(root)
    try:
        assert reopened.project.id == original_id
        assert reopened.project.name == "Original"
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "stage", ["after_root", "after_directories", "after_manifest"]
)
def test_injected_failure_at_each_creation_boundary_is_bounded(
    tmp_path: Path,
    stage: str,
) -> None:
    root = tmp_path / stage

    def failpoint(current_stage: str) -> None:
        if current_stage == stage:
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        create_project(root, "Demo", failpoint=failpoint)

    assert not (root / "project.json").exists()
    assert not (root / "project.fidelichem.sqlite").exists()
    assert not any(
        (root / directory).exists() for directory in ("artifacts", "cache")
    )


@pytest.mark.parametrize("bad_root", ["file", "nonempty"])
def test_existing_root_conflicts_are_rejected_without_writes(
    tmp_path: Path,
    bad_root: str,
) -> None:
    root = tmp_path / bad_root
    if bad_root == "file":
        root.write_text("do not replace", encoding="utf-8")
    else:
        root.mkdir()
        (root / "existing.txt").write_text("do not replace", encoding="utf-8")

    with pytest.raises(ProjectConflictError):
        create_project(root, "Demo")

    assert root.exists()
    if root.is_file():
        assert root.read_text(encoding="utf-8") == "do not replace"
    else:
        assert (root / "existing.txt").read_text(encoding="utf-8") == "do not replace"


@pytest.mark.parametrize(
    "database",
    [
        "../outside.sqlite",
        "/tmp/outside.sqlite",
        "C:/outside.sqlite",
        r"C:\\outside.sqlite",
    ],
)
def test_unsafe_manifest_database_path_is_rejected(
    tmp_path: Path,
    database: str,
) -> None:
    root = tmp_path / "Demo"
    root.mkdir()
    for directory in ("artifacts", "cache", "exports", "logs"):
        (root / directory).mkdir()
    (root / "project.json").write_bytes(
        canonical_json_bytes(
            {
                "database": database,
                "name": "Demo",
                "project_id": "11111111-1111-4111-8111-111111111111",
                "schema_version": 1,
            }
        )
    )

    with pytest.raises((UnsafeManifestPathError, ProjectManifestError)):
        open_project(root)


@pytest.mark.parametrize(
    "field,value",
    [
        ("database", None),
        ("name", None),
        ("project_id", None),
        ("schema_version", "1"),
    ],
)
def test_manifest_field_types_are_validated_safely(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    root = tmp_path / field
    root.mkdir()
    for directory in ("artifacts", "cache", "exports", "logs"):
        (root / directory).mkdir()
    manifest: dict[str, object] = {
        "database": "project.fidelichem.sqlite",
        "name": "Demo",
        "project_id": "11111111-1111-4111-8111-111111111111",
        "schema_version": 1,
    }
    manifest[field] = value
    (root / "project.json").write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(ProjectManifestError):
        open_project(root)


def test_noncanonical_manifest_and_unknown_keys_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "Demo"
    root.mkdir()
    for directory in ("artifacts", "cache", "exports", "logs"):
        (root / directory).mkdir()
    manifest = {
        "database": "project.fidelichem.sqlite",
        "name": "Demo",
        "project_id": "11111111-1111-4111-8111-111111111111",
        "schema_version": 1,
        "extra": True,
    }
    (root / "project.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ProjectManifestError):
        open_project(root)


def test_injected_creation_failure_cleans_only_new_targets(tmp_path: Path) -> None:
    root = tmp_path / "Demo"
    root.mkdir()

    def failpoint(stage: str) -> None:
        if stage == "after_database":
            (root / "keep.txt").write_text("user data", encoding="utf-8")
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        create_project(root, "Demo", failpoint=failpoint)

    assert (root / "keep.txt").read_text(encoding="utf-8") == "user data"
    assert not (root / "project.json").exists()
    assert not (root / "project.fidelichem.sqlite").exists()
    assert not (root / "artifacts").exists()


def test_end_to_end_provenance_survives_close_reopen_and_rollback(
    tmp_path: Path,
) -> None:
    paths = create_project(tmp_path / "Evidence", "Evidence")
    batch = ImportBatch(
        project_id=paths.project.id,
        adapter_id="test",
        adapter_version="1",
        started_at=NOW,
        source_root="inputs",
    )
    artifact = SourceArtifact(
        import_batch_id=batch.id,
        path="C:/inputs/ligand.sdf",
        relative_path="ligand.sdf",
        sha256=HASH,
        file_type="sdf",
        size_bytes=12,
        mtime=NOW,
    )
    from fidelichem.storage.services import StorageService

    service = StorageService(paths.engine)
    service.create_import_batch(batch)
    with UnitOfWork(paths.engine) as uow:
        uow.source_artifacts.add(artifact)
    service.complete_import_batch(batch.id, completed_at=NOW + timedelta(hours=1))
    service.rollback_import_batch(batch.id, reason="withdrawn")
    paths.close()

    reopened = open_project(tmp_path / "Evidence")
    try:
        with UnitOfWork(reopened.engine) as uow:
            stored_batch = uow.import_batches.get(batch.id)
            assert stored_batch is not None
            assert stored_batch.status is ImportStatus.ROLLED_BACK
            assert stored_batch.rollback_reason == "withdrawn"
            assert uow.source_artifacts.get(artifact.id) == artifact
            events = uow.audit_events.list_by_batch(batch.id)
            assert [event.action for event in events] == [
                "import.created",
                "import.completed",
                "import.rolled_back",
            ]
    finally:
        reopened.close()


def test_missing_project_database_is_a_safe_manifest_error(tmp_path: Path) -> None:
    root = tmp_path / "Demo"
    root.mkdir()
    (root / "project.json").write_text(
        '{"database":"project.fidelichem.sqlite","name":"Demo",'
        '"project_id":"11111111-1111-4111-8111-111111111111",'
        '"schema_version":1}',
        encoding="utf-8",
    )
    with pytest.raises(ProjectManifestError):
        open_project(root)


def test_open_missing_root_and_incomplete_layout_are_safe_errors(
    tmp_path: Path,
) -> None:
    with pytest.raises(ProjectManifestError):
        open_project(tmp_path / "missing")

    root = tmp_path / "incomplete"
    root.mkdir()
    (root / "project.json").write_bytes(
        canonical_json_bytes(
            {
                "database": "project.fidelichem.sqlite",
                "name": "Demo",
                "project_id": "11111111-1111-4111-8111-111111111111",
                "schema_version": 1,
            }
        )
    )
    with pytest.raises(ProjectManifestError):
        open_project(root)


def test_read_only_reopen_rejects_storage_writes(tmp_path: Path) -> None:
    created = create_project(tmp_path / "Demo", "Demo")
    created.close()
    reopened = open_project(tmp_path / "Demo", read_only=True)
    try:
        with (
            pytest.raises((OperationalError, ProjectManifestError, StorageWriteError)),
            UnitOfWork(reopened.engine) as uow,
        ):
            uow.projects.add(reopened.project.model_copy(update={"name": "Other"}))
    finally:
        reopened.close()


def test_open_rejects_manifest_database_mismatch_safely(tmp_path: Path) -> None:
    created = create_project(tmp_path / "Demo", "Demo")
    created.close()
    manifest = json.loads((tmp_path / "Demo" / "project.json").read_text())
    manifest["name"] = "Changed"
    (tmp_path / "Demo" / "project.json").write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(ProjectManifestError):
        open_project(tmp_path / "Demo")


def test_open_rejects_a_moved_database_even_when_manifest_path_is_in_root(
    tmp_path: Path,
) -> None:
    created = create_project(tmp_path / "Demo", "Demo")
    created.close()
    root = tmp_path / "Demo"
    nested = root / "nested"
    nested.mkdir()
    created.database.rename(nested / "db.sqlite")
    manifest = json.loads(created.manifest.read_text(encoding="utf-8"))
    manifest["database"] = "nested/db.sqlite"
    created.manifest.write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(ProjectManifestError):
        open_project(root)

    assert (nested / "db.sqlite").is_file()


@pytest.mark.parametrize("schema_version", [True, False])
def test_manifest_schema_version_rejects_boolean_values(
    tmp_path: Path,
    schema_version: bool,
) -> None:
    created = create_project(tmp_path / "Demo", "Demo")
    created.close()
    manifest = json.loads(created.manifest.read_text(encoding="utf-8"))
    manifest["schema_version"] = schema_version
    created.manifest.write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(ProjectManifestError):
        open_project(created.root)


def test_creation_migration_failure_cleans_created_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_upgrade(_engine: object) -> None:
        raise MigrationError("migration details must not escape")

    monkeypatch.setattr(project_service, "upgrade_database", fail_upgrade)
    root = tmp_path / "Demo"
    with pytest.raises(ProjectManifestError):
        create_project(root, "Demo")

    assert not root.exists()
