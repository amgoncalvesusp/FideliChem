from __future__ import annotations

import runpy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.runner import (
    MigrationError,
    assert_database_current,
    current_revision,
    head_revision,
    upgrade_database,
)

PROJECT_ID = "11111111-1111-4111-8111-111111111111"
PROJECT_ID_2 = "22222222-2222-4222-8222-222222222222"
BATCH_ID = "33333333-3333-4333-8333-333333333333"
AUDIT_ID = "44444444-4444-4444-8444-444444444444"
ARTIFACT_ID = "55555555-5555-4555-8555-555555555555"


def _insert_project(connection: object, project_id: str = PROJECT_ID) -> None:
    assert hasattr(connection, "execute")
    connection.execute(
        text(
            "INSERT INTO project "
            "(id, name, created_at, updated_at, schema_version) "
            "VALUES (:id, :name, :created, :updated, :version)"
        ),
        {
            "id": project_id,
            "name": "Test project",
            "created": "2026-01-01T00:00:00.000000Z",
            "updated": "2026-01-01T00:00:00.000000Z",
            "version": 1,
        },
    )


def _insert_batch(
    connection: object,
    project_id: str = PROJECT_ID,
) -> None:
    assert hasattr(connection, "execute")
    connection.execute(
        text(
            "INSERT INTO import_batch "
            "(id, project_id, adapter_id, adapter_version, started_at, "
            "source_root, file_count, warnings_json, status) VALUES "
            "(:id, :project, :adapter, :version, :started, :root, :count, "
            ":warnings, :status)"
        ),
        {
            "id": BATCH_ID,
            "project": project_id,
            "adapter": "test",
            "version": "1.0",
            "started": "2026-01-01T00:00:00.000000Z",
            "root": "source",
            "count": 1,
            "warnings": "[]",
            "status": "in_progress",
        },
    )


def _insert_audit(connection: object, audit_id: str = AUDIT_ID) -> None:
    assert hasattr(connection, "execute")
    connection.execute(
        text(
            "INSERT INTO audit_event "
            "(id, timestamp, action, entity_type, entity_id, source, actor_kind) "
            "VALUES (:id, :timestamp, :action, :type, :entity, :source, :actor)"
        ),
        {
            "id": audit_id,
            "timestamp": "2026-01-01T00:00:00.000000Z",
            "action": "created",
            "type": "project",
            "entity": PROJECT_ID,
            "source": "test",
            "actor": "system",
        },
    )


def test_blank_database_migrates_to_head_and_has_expected_objects(
    database_path: Path,
) -> None:
    engine = create_sqlite_engine(database_path)
    assert current_revision(engine) is None

    upgrade_database(engine)
    assert current_revision(engine) == head_revision()
    assert_database_current(engine)

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "alembic_version",
        "audit_event",
        "alias",
        "compound",
        "identity_resolution",
        "import_batch",
        "molecular_state",
        "project",
        "source_artifact",
    }
    assert inspector.get_indexes("import_batch")
    assert inspector.get_indexes("source_artifact")
    assert inspector.get_indexes("audit_event")
    with engine.connect() as connection:
        trigger_names = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
            )
        }
    assert {
        "trg_project_single_row",
        "trg_project_immutable",
        "trg_import_batch_immutable",
        "trg_source_artifact_no_update",
        "trg_source_artifact_no_delete",
        "trg_audit_event_no_explicit_sequence",
        "trg_audit_event_no_explicit_rowid",
        "trg_audit_event_sequence",
        "trg_audit_event_sequence_assign",
        "trg_audit_event_no_update",
        "trg_audit_event_no_delete",
        "trg_compound_no_update",
        "trg_compound_no_delete",
        "trg_molecular_state_no_update",
        "trg_molecular_state_no_delete",
        "trg_alias_no_update",
        "trg_alias_no_delete",
        "trg_identity_resolution_validate_insert",
        "trg_identity_resolution_no_update",
        "trg_identity_resolution_no_delete",
    }.issubset(trigger_names)
    engine.dispose()


def test_repeated_upgrade_and_reopen_are_safe(database_path: Path) -> None:
    first = create_sqlite_engine(database_path)
    upgrade_database(first)
    first.dispose()

    reopened = create_sqlite_engine(database_path)
    upgrade_database(reopened)
    assert current_revision(reopened) == head_revision()
    assert_database_current(reopened)
    reopened.dispose()


def test_orm_metadata_has_no_unplanned_upgrade_operations(
    database_path: Path,
) -> None:
    engine = create_sqlite_engine(database_path)
    upgrade_database(engine)
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path("src/fidelichem/storage/migrations").resolve()),
    )
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.check(config)
    engine.dispose()


def test_alembic_environment_rejects_missing_existing_connection() -> None:
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path("src/fidelichem/storage/migrations").resolve()),
    )
    script = ScriptDirectory.from_config(config)
    environment = Path("src/fidelichem/storage/migrations/env.py").resolve()
    with (
        EnvironmentContext(config, script),
        pytest.raises(
            RuntimeError,
            match="existing SQLAlchemy connection",
        ),
    ):
        runpy.run_path(str(environment), run_name="fidelichem_storage_env")


def test_integrity_and_foreign_key_checks_are_clean(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
        assert list(connection.execute(text("PRAGMA foreign_key_check"))) == []


def test_project_is_singleton_and_foreign_keys_are_restrictive(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        with pytest.raises(IntegrityError):
            _insert_project(connection, PROJECT_ID_2)
        with pytest.raises(IntegrityError):
            _insert_batch(connection, PROJECT_ID_2)


def test_audit_batch_correlation_requires_existing_parent(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO audit_event "
                    "(id, timestamp, action, entity_type, entity_id, "
                    "import_batch_id, source, actor_kind) VALUES "
                    "(:id, :timestamp, :action, :type, :entity, :batch, "
                    ":source, :actor)"
                ),
                {
                    "id": AUDIT_ID,
                    "timestamp": "2026-01-01T00:00:00.000000Z",
                    "action": "created",
                    "type": "batch",
                    "entity": BATCH_ID,
                    "batch": BATCH_ID,
                    "source": "test",
                    "actor": "system",
                },
            )


def test_unknown_or_future_revision_is_rejected_before_upgrade(
    database_path: Path,
) -> None:
    engine = create_sqlite_engine(database_path)
    upgrade_database(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'future'"))

    with pytest.raises(MigrationError):
        upgrade_database(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "future"
        )
    engine.dispose()


def test_migration_runner_does_not_use_metadata_create_all() -> None:
    source_files = (
        Path("src/fidelichem/storage/engine.py"),
        Path("src/fidelichem/storage/orm.py"),
        Path("src/fidelichem/storage/runner.py"),
        Path("src/fidelichem/storage/migrations/env.py"),
        Path("src/fidelichem/storage/migrations/versions/0001_initial_storage.py"),
        Path("src/fidelichem/storage/migrations/versions/0002_chemistry_identity.py"),
    )
    for source_file in source_files:
        assert "metadata.create_all" not in source_file.read_text(encoding="utf-8")


def test_direct_sql_rejects_second_project_and_immutable_artifact_audit_rows(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        _insert_batch(connection)
        connection.execute(
            text(
                "INSERT INTO source_artifact "
                "(id, import_batch_id, path, relative_path, sha256, file_type, "
                "size_bytes, mtime) VALUES (:id, :batch, :path, :relative, :sha, "
                ":type, :size, :mtime)"
            ),
            {
                "id": ARTIFACT_ID,
                "batch": BATCH_ID,
                "path": "/tmp/input.csv",
                "relative": "input.csv",
                "sha": "a" * 64,
                "type": "csv",
                "size": 4,
                "mtime": "2026-01-01T00:00:00.000000Z",
            },
        )
        _insert_audit(connection)

        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text("UPDATE source_artifact SET path = 'changed' WHERE id = :id"),
                {"id": ARTIFACT_ID},
            )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text("DELETE FROM source_artifact WHERE id = :id"),
                {"id": ARTIFACT_ID},
            )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text("UPDATE audit_event SET action = 'changed' WHERE id = :id"),
                {"id": AUDIT_ID},
            )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text("DELETE FROM audit_event WHERE id = :id"),
                {"id": AUDIT_ID},
            )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    "INSERT OR REPLACE INTO source_artifact "
                    "(id, import_batch_id, path, relative_path, sha256, file_type, "
                    "size_bytes, mtime) VALUES (:id, :batch, :path, :relative, "
                    ":sha, :type, :size, :mtime)"
                ),
                {
                    "id": ARTIFACT_ID,
                    "batch": BATCH_ID,
                    "path": "/tmp/replaced.csv",
                    "relative": "input.csv",
                    "sha": "b" * 64,
                    "type": "csv",
                    "size": 9,
                    "mtime": "2026-01-01T00:00:00.000000Z",
                },
            )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    "INSERT OR REPLACE INTO audit_event "
                    "(id, timestamp, action, entity_type, entity_id, source, "
                    "actor_kind) VALUES (:id, :timestamp, :action, :type, "
                    ":entity, :source, :actor)"
                ),
                {
                    "id": AUDIT_ID,
                    "timestamp": "2026-01-01T00:00:00.000000Z",
                    "action": "replaced",
                    "type": "project",
                    "entity": PROJECT_ID,
                    "source": "test",
                    "actor": "system",
                },
            )


def test_project_and_batch_rows_reject_physical_deletion(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        _insert_batch(connection)
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text("DELETE FROM import_batch WHERE id = :id"),
                {"id": BATCH_ID},
            )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text("DELETE FROM project WHERE id = :id"),
                {"id": PROJECT_ID},
            )


def test_direct_audit_insert_cannot_choose_sequence_and_committed_sequence_increases(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        _insert_audit(connection, AUDIT_ID)
        _insert_audit(connection, "66666666-6666-4666-8666-666666666666")
        sequences = [
            int(row[0])
            for row in connection.execute(
                text("SELECT sequence FROM audit_event ORDER BY sequence")
            )
        ]
    assert sequences == sorted(sequences)
    assert sequences[0] < sequences[1]
    assert all(sequence > 0 for sequence in sequences)


def test_audit_sequence_remains_increasing_after_database_reopen(
    database_path: Path,
) -> None:
    first = create_sqlite_engine(database_path)
    upgrade_database(first)
    with first.begin() as connection:
        _insert_project(connection)
        _insert_audit(connection)
    first.dispose()

    reopened = create_sqlite_engine(database_path)
    with reopened.begin() as connection:
        _insert_audit(connection, "66666666-6666-4666-8666-666666666666")
        sequences = [
            int(row[0])
            for row in connection.execute(
                text("SELECT sequence FROM audit_event ORDER BY sequence")
            )
        ]
    reopened.dispose()
    assert sequences[0] > 0
    assert sequences[1] > sequences[0]


def test_audit_insert_with_explicit_sequence_is_rejected(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    "INSERT INTO audit_event "
                    "(id, sequence, timestamp, action, entity_type, entity_id, "
                    "source, actor_kind) VALUES (:id, 987654, :timestamp, :action, "
                    ":type, :entity, :source, :actor)"
                ),
                {
                    "id": AUDIT_ID,
                    "timestamp": "2026-01-01T00:00:00.000000Z",
                    "action": "created",
                    "type": "project",
                    "entity": PROJECT_ID,
                    "source": "test",
                    "actor": "system",
                },
            )


@pytest.mark.parametrize(
    ("rowid_alias", "rowid_value"),
    [
        ("rowid", 99),
        ("_rowid_", 100),
        ("oid", 101),
        ("rowid", 0),
        ("_rowid_", -1),
        ("oid", -2),
    ],
)
def test_direct_audit_insert_cannot_choose_rowid_alias(
    migrated_engine: Engine,
    rowid_alias: str,
    rowid_value: int,
) -> None:
    audit_id = f"{abs(rowid_value) + 10:08d}-1111-4111-8111-111111111111"
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    f"INSERT INTO audit_event ({rowid_alias}, id, timestamp, "
                    "action, entity_type, entity_id, source, actor_kind) VALUES "
                    "(:rowid, :id, :timestamp, :action, :type, :entity, "
                    ":source, :actor)"
                ),
                {
                    "rowid": rowid_value,
                    "id": audit_id,
                    "timestamp": "2026-01-01T00:00:00.000000Z",
                    "action": "created",
                    "type": "project",
                    "entity": PROJECT_ID,
                    "source": "test",
                    "actor": "system",
                },
            )


@pytest.mark.parametrize(
    "relative_path",
    ["../x", "a/../x", "/abs", "C:/abs", r"C:\abs", "nul\x00path"],
)
def test_direct_sql_rejects_unsafe_relative_paths(
    migrated_engine: Engine,
    relative_path: str,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        _insert_batch(connection)
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    "INSERT INTO source_artifact "
                    "(id, import_batch_id, path, relative_path, sha256, file_type, "
                    "size_bytes, mtime) VALUES (:id, :batch, :path, :relative, "
                    ":sha, :type, :size, :mtime)"
                ),
                {
                    "id": "77777777-7777-4777-8777-777777777777",
                    "batch": BATCH_ID,
                    "path": "/tmp/input.csv",
                    "relative": relative_path,
                    "sha": "a" * 64,
                    "type": "csv",
                    "size": 4,
                    "mtime": "2026-01-01T00:00:00.000000Z",
                },
            )


@pytest.mark.parametrize(
    "relative_path",
    ["a//b.sdf", "a/./b.sdf", "./a.sdf", "a.sdf/", ".", "a/.", "a//"],
)
def test_direct_sql_rejects_noncanonical_relative_paths(
    migrated_engine: Engine,
    relative_path: str,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        _insert_batch(connection)
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    "INSERT INTO source_artifact "
                    "(id, import_batch_id, path, relative_path, sha256, file_type, "
                    "size_bytes, mtime) VALUES (:id, :batch, :path, :relative, "
                    ":sha, :type, :size, :mtime)"
                ),
                {
                    "id": "88888888-8888-4888-8888-888888888888",
                    "batch": BATCH_ID,
                    "path": "/tmp/input.sdf",
                    "relative": relative_path,
                    "sha": "a" * 64,
                    "type": "sdf",
                    "size": 4,
                    "mtime": "2026-01-01T00:00:00.000000Z",
                },
            )


def test_direct_sql_accepts_canonical_nested_relative_path(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        _insert_batch(connection)
        connection.execute(
            text(
                "INSERT INTO source_artifact "
                "(id, import_batch_id, path, relative_path, sha256, file_type, "
                "size_bytes, mtime) VALUES (:id, :batch, :path, :relative, "
                ":sha, :type, :size, :mtime)"
            ),
            {
                "id": "99999999-9999-4999-8999-999999999999",
                "batch": BATCH_ID,
                "path": "/tmp/input.sdf",
                "relative": "nested/input.sdf",
                "sha": "a" * 64,
                "type": "sdf",
                "size": 4,
                "mtime": "2026-01-01T00:00:00.000000Z",
            },
        )
        assert (
            connection.scalar(
                text("SELECT relative_path FROM source_artifact WHERE id = :id"),
                {"id": "99999999-9999-4999-8999-999999999999"},
            )
            == "nested/input.sdf"
        )


def test_import_batch_immutable_fields_are_database_enforced(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        _insert_batch(connection)
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text("UPDATE import_batch SET adapter_id = 'other' WHERE id = :id"),
                {"id": BATCH_ID},
            )


def test_project_immutable_fields_are_database_enforced(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text("UPDATE project SET schema_version = 2 WHERE id = :id"),
                {"id": PROJECT_ID},
            )
        connection.execute(
            text("UPDATE project SET name = :name, description = :description"),
            {"name": "Renamed", "description": "Metadata"},
        )
        assert connection.scalar(text("SELECT name FROM project")) == "Renamed"


def test_timestamps_are_stored_as_utc_text(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        _insert_project(connection)
        raw = connection.scalar(text("SELECT created_at FROM project"))
    assert raw.endswith("Z")
    parsed = datetime.fromisoformat(raw.removesuffix("Z") + "+00:00")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == UTC.utcoffset(parsed)
