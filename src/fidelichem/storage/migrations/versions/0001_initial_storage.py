"""Create the initial immutable Phase 1 storage schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_storage"  # pragma: no cover
down_revision = None  # pragma: no cover
branch_labels = None  # pragma: no cover
depends_on = None  # pragma: no cover


def upgrade() -> None:  # pragma: no cover
    op.create_table(
        "project",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_project_name_nonblank"),
        sa.CheckConstraint(
            "schema_version >= 1",
            name="ck_project_schema_version_positive",
        ),
        sa.CheckConstraint(
            "created_at LIKE '%Z'",
            name="ck_project_created_at_utc",
        ),
        sa.CheckConstraint(
            "updated_at LIKE '%Z'",
            name="ck_project_updated_at_utc",
        ),
    )
    op.create_table(
        "import_batch",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("adapter_id", sa.Text(), nullable=False),
        sa.Column("adapter_version", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'in_progress'"),
        ),
        sa.Column("source_root", sa.Text(), nullable=False),
        sa.Column(
            "file_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column(
            "warnings_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("rolled_back_at", sa.Text(), nullable=True),
        sa.Column("rollback_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_import_batch"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name="fk_import_batch_project",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'failed', 'rolled_back')",
            name="ck_import_batch_status",
        ),
        sa.CheckConstraint("length(trim(adapter_id)) > 0", name="ck_batch_adapter_id"),
        sa.CheckConstraint(
            "length(trim(adapter_version)) > 0",
            name="ck_batch_adapter_version",
        ),
        sa.CheckConstraint(
            "length(trim(source_root)) > 0",
            name="ck_batch_source_root",
        ),
        sa.CheckConstraint("file_count >= 0", name="ck_batch_file_count"),
        sa.CheckConstraint("started_at LIKE '%Z'", name="ck_batch_started_at_utc"),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at LIKE '%Z'",
            name="ck_batch_completed_at_utc",
        ),
        sa.CheckConstraint(
            "rolled_back_at IS NULL OR rolled_back_at LIKE '%Z'",
            name="ck_batch_rolled_back_at_utc",
        ),
        sa.CheckConstraint(
            "input_hash IS NULL OR (length(input_hash) = 64 AND "
            "input_hash = lower(input_hash) AND input_hash NOT GLOB '*[^0-9a-f]*')",
            name="ck_batch_input_hash",
        ),
        sa.CheckConstraint("json_valid(warnings_json)", name="ck_batch_warnings_json"),
    )
    op.create_index("ix_import_batch_project_id", "import_batch", ["project_id"])
    op.create_index("ix_import_batch_adapter_id", "import_batch", ["adapter_id"])
    op.create_index("ix_import_batch_input_hash", "import_batch", ["input_hash"])

    op.create_table(
        "source_artifact",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("import_batch_id", sa.String(36), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("mtime", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_source_artifact"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batch.id"],
            name="fk_source_artifact_import_batch",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_batch_id",
            "relative_path",
            name="uq_source_artifact_batch_relative_path",
        ),
        sa.CheckConstraint("length(trim(path)) > 0", name="ck_artifact_path"),
        sa.CheckConstraint(
            "length(trim(relative_path)) > 0",
            name="ck_artifact_relative_path",
        ),
        sa.CheckConstraint(
            "length(trim(relative_path)) > 0 AND "
            "instr(relative_path, char(0)) = 0 AND "
            "instr(relative_path, char(92)) = 0 AND "
            "substr(relative_path, 1, 1) <> '/' AND "
            "relative_path NOT GLOB '[A-Za-z]:*' AND "
            "relative_path <> '..' AND "
            "relative_path NOT LIKE '../%' AND "
            "relative_path NOT LIKE '%/../%' AND "
            "relative_path NOT LIKE '%/..'",
            name="ck_artifact_relative_path_safe",
        ),
        sa.CheckConstraint(
            "length(sha256) = 64 AND sha256 = lower(sha256) AND "
            "sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_artifact_sha256",
        ),
        sa.CheckConstraint("length(trim(file_type)) > 0", name="ck_artifact_file_type"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_artifact_size_bytes"),
        sa.CheckConstraint("mtime LIKE '%Z'", name="ck_artifact_mtime_utc"),
    )
    op.create_index(
        "ix_source_artifact_import_batch_id",
        "source_artifact",
        ["import_batch_id"],
    )
    op.create_index("ix_source_artifact_sha256", "source_artifact", ["sha256"])

    op.create_table(
        "audit_event",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("import_batch_id", sa.String(36), nullable=True),
        sa.Column("old_value_json", sa.Text(), nullable=True),
        sa.Column("new_value_json", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "actor_kind",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'system'"),
        ),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_audit_event"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batch.id"],
            name="fk_audit_event_import_batch",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("length(trim(action)) > 0", name="ck_audit_action"),
        sa.CheckConstraint(
            "length(trim(entity_type)) > 0",
            name="ck_audit_entity_type",
        ),
        sa.CheckConstraint("length(trim(entity_id)) > 0", name="ck_audit_entity_id"),
        sa.CheckConstraint("length(trim(source)) > 0", name="ck_audit_source"),
        sa.CheckConstraint(
            "actor_kind IN ('user', 'system')",
            name="ck_audit_actor_kind",
        ),
        sa.CheckConstraint("timestamp LIKE '%Z'", name="ck_audit_timestamp_utc"),
        sa.CheckConstraint(
            "old_value_json IS NULL OR json_valid(old_value_json)",
            name="ck_audit_old_json",
        ),
        sa.CheckConstraint(
            "new_value_json IS NULL OR json_valid(new_value_json)",
            name="ck_audit_new_json",
        ),
        sa.UniqueConstraint("sequence", name="uq_audit_event_sequence"),
    )
    op.create_index(
        "ix_audit_event_import_batch_id",
        "audit_event",
        ["import_batch_id"],
    )
    op.create_index(
        "ix_audit_event_entity",
        "audit_event",
        ["entity_type", "entity_id"],
    )
    op.create_index("ix_audit_event_sequence", "audit_event", ["sequence"])

    op.execute(
        """
        CREATE TRIGGER trg_project_single_row
        BEFORE INSERT ON project
        WHEN EXISTS (SELECT 1 FROM project)
        BEGIN
            SELECT RAISE(ABORT, 'only one project is allowed per database');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_project_no_delete
        BEFORE DELETE ON project
        BEGIN
            SELECT RAISE(ABORT, 'project rows are permanent');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_import_batch_immutable
        BEFORE UPDATE ON import_batch
        WHEN NEW.id IS NOT OLD.id
          OR NEW.project_id IS NOT OLD.project_id
          OR NEW.adapter_id IS NOT OLD.adapter_id
          OR NEW.adapter_version IS NOT OLD.adapter_version
          OR NEW.started_at IS NOT OLD.started_at
          OR NEW.source_root IS NOT OLD.source_root
          OR NEW.file_count IS NOT OLD.file_count
          OR NEW.input_hash IS NOT OLD.input_hash
          OR NEW.warnings_json IS NOT OLD.warnings_json
        BEGIN
            SELECT RAISE(ABORT, 'import batch immutable fields cannot change');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_import_batch_no_delete
        BEFORE DELETE ON import_batch
        BEGIN
            SELECT RAISE(ABORT, 'import batch rows are permanent');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_source_artifact_no_update
        BEFORE UPDATE ON source_artifact
        BEGIN
            SELECT RAISE(ABORT, 'source artifacts are append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_source_artifact_no_delete
        BEFORE DELETE ON source_artifact
        BEGIN
            SELECT RAISE(ABORT, 'source artifacts are append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_no_explicit_sequence
        BEFORE INSERT ON audit_event
        WHEN NEW.sequence IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'audit sequence is database generated');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_no_explicit_rowid
        BEFORE INSERT ON audit_event
        WHEN NEW.rowid > 0
        BEGIN
            SELECT RAISE(ABORT, 'audit rowid is database generated');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_sequence
        AFTER INSERT ON audit_event
        WHEN NEW.rowid <= 0
        BEGIN
            SELECT RAISE(ABORT, 'audit rowid must be positive');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_sequence_assign
        AFTER INSERT ON audit_event
        BEGIN
            UPDATE audit_event SET sequence = NEW.rowid WHERE id = NEW.id;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_no_update
        BEFORE UPDATE ON audit_event
        WHEN NOT (
            NEW.sequence = OLD.rowid
            AND NEW.id IS OLD.id
            AND NEW.timestamp IS OLD.timestamp
            AND NEW.action IS OLD.action
            AND NEW.entity_type IS OLD.entity_type
            AND NEW.entity_id IS OLD.entity_id
            AND NEW.import_batch_id IS OLD.import_batch_id
            AND NEW.old_value_json IS OLD.old_value_json
            AND NEW.new_value_json IS OLD.new_value_json
            AND NEW.source IS OLD.source
            AND NEW.actor_kind IS OLD.actor_kind
            AND NEW.actor_id IS OLD.actor_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'audit events are append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_no_delete
        BEFORE DELETE ON audit_event
        BEGIN
            SELECT RAISE(ABORT, 'audit events are append-only');
        END
        """
    )


def downgrade() -> None:  # pragma: no cover
    op.execute("DROP TRIGGER IF EXISTS trg_audit_event_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_event_no_update")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_event_sequence_assign")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_event_sequence")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_event_no_explicit_rowid")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_event_no_explicit_sequence")
    op.execute("DROP TRIGGER IF EXISTS trg_source_artifact_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_source_artifact_no_update")
    op.execute("DROP TRIGGER IF EXISTS trg_import_batch_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_import_batch_immutable")
    op.execute("DROP TRIGGER IF EXISTS trg_project_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_project_single_row")
    op.drop_index("ix_audit_event_sequence", table_name="audit_event")
    op.drop_index("ix_audit_event_entity", table_name="audit_event")
    op.drop_index("ix_audit_event_import_batch_id", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_index("ix_source_artifact_sha256", table_name="source_artifact")
    op.drop_index("ix_source_artifact_import_batch_id", table_name="source_artifact")
    op.drop_table("source_artifact")
    op.drop_index("ix_import_batch_input_hash", table_name="import_batch")
    op.drop_index("ix_import_batch_adapter_id", table_name="import_batch")
    op.drop_index("ix_import_batch_project_id", table_name="import_batch")
    op.drop_table("import_batch")
    op.drop_table("project")
