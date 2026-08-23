"""Persist canonical computational evidence with explicit provenance links."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_evidence"  # pragma: no cover
down_revision = "0002_chemistry_identity"  # pragma: no cover
branch_labels = None  # pragma: no cover
depends_on = None  # pragma: no cover


def _hash_check(column: str, name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{column} IS NULL OR (length({column}) = 64 AND "
        f"{column} = lower({column}) AND {column} NOT GLOB '*[^0-9a-f]*')",
        name=name,
    )


def _immutable_trigger(table: str) -> None:
    op.execute(
        f"""
        CREATE TRIGGER trg_{table}_immutable
        BEFORE UPDATE ON {table}
        BEGIN
            SELECT RAISE(ABORT, '{table} rows are immutable');
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_{table}_no_delete
        BEFORE DELETE ON {table}
        BEGIN
            SELECT RAISE(ABORT, '{table} rows are permanent');
        END
        """
    )


def upgrade() -> None:  # pragma: no cover
    op.create_table(
        "evidence_target",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("import_batch_id", sa.String(36), nullable=False),
        sa.Column("source_artifact_id", sa.String(36), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("accession", sa.Text(), nullable=True),
        sa.Column("pdb_id", sa.Text(), nullable=True),
        sa.Column("chain", sa.Text(), nullable=True),
        sa.Column("sequence_hash", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_target"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batch.id"],
            name="fk_evidence_target_batch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["source_artifact.id"],
            name="fk_evidence_target_artifact",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_batch_id", "name", name="uq_evidence_target_batch_name"
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_evidence_target_name"),
        _hash_check("sequence_hash", "ck_evidence_target_sequence_hash"),
    )
    op.create_index(
        "ix_evidence_target_import_batch_id", "evidence_target", ["import_batch_id"]
    )

    op.create_table(
        "docking_run",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("import_batch_id", sa.String(36), nullable=False),
        sa.Column("source_artifact_id", sa.String(36), nullable=True),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("run_name", sa.Text(), nullable=False),
        sa.Column("target_name", sa.Text(), nullable=True),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=True),
        sa.Column("configuration_hash", sa.String(64), nullable=True),
        sa.Column(
            "parameters_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.PrimaryKeyConstraint("id", name="pk_docking_run"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batch.id"],
            name="fk_docking_run_batch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["source_artifact.id"],
            name="fk_docking_run_artifact",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["evidence_target.id"],
            name="fk_docking_run_target",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_batch_id", "run_name", name="uq_docking_run_batch_name"
        ),
        sa.CheckConstraint("length(trim(run_name)) > 0", name="ck_docking_run_name"),
        sa.CheckConstraint("length(trim(engine)) > 0", name="ck_docking_run_engine"),
        _hash_check("configuration_hash", "ck_docking_run_config_hash"),
        sa.CheckConstraint(
            "json_valid(parameters_json)", name="ck_docking_run_parameters_json"
        ),
    )
    op.create_index(
        "ix_docking_run_import_batch_id", "docking_run", ["import_batch_id"]
    )

    op.create_table(
        "pose",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("import_batch_id", sa.String(36), nullable=False),
        sa.Column("source_artifact_id", sa.String(36), nullable=True),
        sa.Column("docking_run_id", sa.String(36), nullable=False),
        sa.Column("run_name", sa.Text(), nullable=False),
        sa.Column("compound_source_system", sa.Text(), nullable=False),
        sa.Column("compound_source_value", sa.Text(), nullable=False),
        sa.Column("source_pose_id", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("structure_artifact_path", sa.Text(), nullable=True),
        sa.Column("coordinate_hash", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_pose"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batch.id"],
            name="fk_pose_batch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["source_artifact.id"],
            name="fk_pose_artifact",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["docking_run_id"],
            ["docking_run.id"],
            name="fk_pose_docking_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "docking_run_id", "source_pose_id", name="uq_pose_run_source_id"
        ),
        sa.CheckConstraint("length(trim(run_name)) > 0", name="ck_pose_run_name"),
        sa.CheckConstraint(
            "length(trim(compound_source_system)) > 0", name="ck_pose_source_system"
        ),
        sa.CheckConstraint(
            "length(trim(compound_source_value)) > 0", name="ck_pose_source_value"
        ),
        sa.CheckConstraint(
            "length(trim(source_pose_id)) > 0", name="ck_pose_source_id"
        ),
        sa.CheckConstraint("rank >= 1", name="ck_pose_rank"),
        _hash_check("coordinate_hash", "ck_pose_coordinate_hash"),
    )
    op.create_index("ix_pose_import_batch_id", "pose", ["import_batch_id"])
    op.create_index("ix_pose_docking_run_id", "pose", ["docking_run_id"])

    op.create_table(
        "score_observation",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("import_batch_id", sa.String(36), nullable=False),
        sa.Column("source_artifact_id", sa.String(36), nullable=True),
        sa.Column("docking_run_id", sa.String(36), nullable=False),
        sa.Column("pose_id", sa.String(36), nullable=True),
        sa.Column("run_name", sa.Text(), nullable=False),
        sa.Column("compound_source_value", sa.Text(), nullable=False),
        sa.Column("source_pose_id", sa.Text(), nullable=False),
        sa.Column("score_key", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Float(), nullable=False),
        sa.Column("source_artifact_path", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_score_observation"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batch.id"],
            name="fk_score_batch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["source_artifact.id"],
            name="fk_score_artifact",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["docking_run_id"],
            ["docking_run.id"],
            name="fk_score_docking_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pose_id"], ["pose.id"], name="fk_score_pose", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "docking_run_id",
            "source_pose_id",
            "score_key",
            name="uq_score_run_pose_key",
        ),
        sa.CheckConstraint("length(trim(run_name)) > 0", name="ck_score_run_name"),
        sa.CheckConstraint(
            "length(trim(compound_source_value)) > 0", name="ck_score_source_value"
        ),
        sa.CheckConstraint(
            "length(trim(source_pose_id)) > 0", name="ck_score_source_pose_id"
        ),
        sa.CheckConstraint("length(trim(score_key)) > 0", name="ck_score_key"),
        sa.CheckConstraint(
            "raw_value = raw_value AND abs(raw_value) <= 1.7976931348623157e308",
            name="ck_score_finite",
        ),
    )
    op.create_index(
        "ix_score_observation_import_batch_id", "score_observation", ["import_batch_id"]
    )
    op.create_index(
        "ix_score_observation_docking_run_id", "score_observation", ["docking_run_id"]
    )

    op.create_table(
        "interaction",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("import_batch_id", sa.String(36), nullable=False),
        sa.Column("source_artifact_id", sa.String(36), nullable=True),
        sa.Column("docking_run_id", sa.String(36), nullable=True),
        sa.Column("pose_id", sa.String(36), nullable=True),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("run_name", sa.Text(), nullable=False),
        sa.Column("compound_source_value", sa.Text(), nullable=False),
        sa.Column("source_pose_id", sa.Text(), nullable=False),
        sa.Column("residue_name", sa.Text(), nullable=False),
        sa.Column("interaction_type", sa.Text(), nullable=False),
        sa.Column("target_name", sa.Text(), nullable=True),
        sa.Column("residue_number", sa.Integer(), nullable=True),
        sa.Column("chain", sa.Text(), nullable=True),
        sa.Column("distance", sa.Float(), nullable=True),
        sa.Column("angle", sa.Float(), nullable=True),
        sa.Column("energy", sa.Float(), nullable=True),
        sa.Column("frequency", sa.Float(), nullable=True),
        sa.Column("ligand_feature", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.PrimaryKeyConstraint("id", name="pk_interaction"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batch.id"],
            name="fk_interaction_batch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["source_artifact.id"],
            name="fk_interaction_artifact",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["docking_run_id"],
            ["docking_run.id"],
            name="fk_interaction_docking_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pose_id"], ["pose.id"], name="fk_interaction_pose", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["evidence_target.id"],
            name="fk_interaction_target",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "length(trim(run_name)) > 0", name="ck_interaction_run_name"
        ),
        sa.CheckConstraint(
            "length(trim(compound_source_value)) > 0",
            name="ck_interaction_source_value",
        ),
        sa.CheckConstraint(
            "length(trim(source_pose_id)) > 0", name="ck_interaction_source_pose_id"
        ),
        sa.CheckConstraint(
            "length(trim(residue_name)) > 0", name="ck_interaction_residue_name"
        ),
        sa.CheckConstraint(
            "length(trim(interaction_type)) > 0", name="ck_interaction_type"
        ),
        sa.CheckConstraint(
            "json_valid(metadata_json)", name="ck_interaction_metadata_json"
        ),
    )
    op.create_index(
        "ix_interaction_import_batch_id", "interaction", ["import_batch_id"]
    )
    op.create_index("ix_interaction_pose_id", "interaction", ["pose_id"])

    op.create_table(
        "md_run",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("import_batch_id", sa.String(36), nullable=False),
        sa.Column("source_artifact_id", sa.String(36), nullable=True),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("pose_id", sa.String(36), nullable=True),
        sa.Column("run_name", sa.Text(), nullable=False),
        sa.Column("target_name", sa.Text(), nullable=True),
        sa.Column("compound_source_value", sa.Text(), nullable=True),
        sa.Column("source_pose_id", sa.Text(), nullable=True),
        sa.Column("duration_ns", sa.Float(), nullable=True),
        sa.Column("temperature_k", sa.Float(), nullable=True),
        sa.Column("timestep_fs", sa.Float(), nullable=True),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=True),
        sa.Column(
            "parameters_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.PrimaryKeyConstraint("id", name="pk_md_run"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batch.id"],
            name="fk_md_run_batch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["source_artifact.id"],
            name="fk_md_run_artifact",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["evidence_target.id"],
            name="fk_md_run_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pose_id"], ["pose.id"], name="fk_md_run_pose", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("import_batch_id", "run_name", name="uq_md_run_batch_name"),
        sa.CheckConstraint("length(trim(run_name)) > 0", name="ck_md_run_name"),
        sa.CheckConstraint("length(trim(engine)) > 0", name="ck_md_run_engine"),
        sa.CheckConstraint(
            "duration_ns IS NULL OR (duration_ns = duration_ns AND "
            "abs(duration_ns) <= 1.7976931348623157e308)",
            name="ck_md_run_duration_finite",
        ),
        sa.CheckConstraint(
            "temperature_k IS NULL OR (temperature_k = temperature_k AND "
            "abs(temperature_k) <= 1.7976931348623157e308)",
            name="ck_md_run_temperature_finite",
        ),
        sa.CheckConstraint(
            "timestep_fs IS NULL OR (timestep_fs = timestep_fs AND "
            "abs(timestep_fs) <= 1.7976931348623157e308)",
            name="ck_md_run_timestep_finite",
        ),
        sa.CheckConstraint(
            "json_valid(parameters_json)", name="ck_md_run_parameters_json"
        ),
    )
    op.create_index("ix_md_run_import_batch_id", "md_run", ["import_batch_id"])

    op.create_table(
        "md_metric",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("import_batch_id", sa.String(36), nullable=False),
        sa.Column("source_artifact_id", sa.String(36), nullable=True),
        sa.Column("md_run_id", sa.String(36), nullable=False),
        sa.Column("run_name", sa.Text(), nullable=False),
        sa.Column("metric_key", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("mean_value", sa.Float(), nullable=True),
        sa.Column("std_value", sa.Float(), nullable=True),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("compound_source_value", sa.Text(), nullable=True),
        sa.Column("source_pose_id", sa.Text(), nullable=True),
        sa.Column("source_artifact_path", sa.Text(), nullable=True),
        sa.Column(
            "time_points_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "values_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column(
            "metadata_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.PrimaryKeyConstraint("id", name="pk_md_metric"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batch.id"],
            name="fk_md_metric_batch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["source_artifact.id"],
            name="fk_md_metric_artifact",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["md_run_id"], ["md_run.id"], name="fk_md_metric_run", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("md_run_id", "metric_key", name="uq_md_metric_run_key"),
        sa.CheckConstraint("length(trim(run_name)) > 0", name="ck_md_metric_run_name"),
        sa.CheckConstraint("length(trim(metric_key)) > 0", name="ck_md_metric_key"),
        sa.CheckConstraint(
            "json_valid(time_points_json)", name="ck_md_metric_time_points_json"
        ),
        sa.CheckConstraint("json_valid(values_json)", name="ck_md_metric_values_json"),
        sa.CheckConstraint(
            "json_valid(metadata_json)", name="ck_md_metric_metadata_json"
        ),
    )
    op.create_index("ix_md_metric_import_batch_id", "md_metric", ["import_batch_id"])
    op.create_index("ix_md_metric_md_run_id", "md_metric", ["md_run_id"])

    for table in (
        "evidence_target",
        "docking_run",
        "pose",
        "score_observation",
        "interaction",
        "md_run",
        "md_metric",
    ):
        _immutable_trigger(table)


def downgrade() -> None:  # pragma: no cover
    for table in (
        "md_metric",
        "md_run",
        "interaction",
        "score_observation",
        "pose",
        "docking_run",
        "evidence_target",
    ):
        op.drop_table(table)
