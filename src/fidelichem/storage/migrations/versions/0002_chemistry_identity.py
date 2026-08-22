"""Add immutable chemistry identity and resolution history tables."""

# SQL expressions are kept byte-for-byte aligned with the ORM metadata.
# ruff: noqa: E501

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_chemistry_identity"  # pragma: no cover
down_revision = "0001_initial_storage"  # pragma: no cover
branch_labels = None  # pragma: no cover
depends_on = None  # pragma: no cover

_INCHI = (
    "{column} IS NULL OR (length({column}) = 27 AND "
    "substr({column}, 15, 1) = '-' AND substr({column}, 26, 1) = '-' AND "
    "substr({column}, 1, 14) NOT GLOB '*[^A-Z]*' AND "
    "substr({column}, 16, 10) NOT GLOB '*[^A-Z]*' AND "
    "substr({column}, 27, 1) GLOB '[A-Z]')"
)


def upgrade() -> None:  # pragma: no cover
    op.create_table(
        "compound",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("canonical_smiles", sa.Text(), nullable=False),
        sa.Column("isomeric_smiles", sa.Text(), nullable=False),
        sa.Column("inchikey", sa.String(27), nullable=True),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("molecular_weight", sa.Float(), nullable=False),
        sa.Column("structure_hash", sa.String(64), nullable=False),
        sa.Column("chemistry_policy_id", sa.Text(), nullable=False),
        sa.Column("rdkit_version", sa.Text(), nullable=False),
        sa.Column("inchi_version", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_compound"),
        sa.UniqueConstraint("structure_hash", name="uq_compound_structure_hash"),
        sa.CheckConstraint(
            "length(trim(canonical_smiles)) > 0", name="ck_compound_canonical_smiles"
        ),
        sa.CheckConstraint(
            "length(trim(isomeric_smiles)) > 0", name="ck_compound_isomeric_smiles"
        ),
        sa.CheckConstraint("length(trim(formula)) > 0", name="ck_compound_formula"),
        sa.CheckConstraint("molecular_weight > 0", name="ck_compound_molecular_weight"),
        sa.CheckConstraint(
            "length(structure_hash) = 64 AND structure_hash = lower(structure_hash) AND structure_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_compound_structure_hash",
        ),
        sa.CheckConstraint(
            "length(trim(chemistry_policy_id)) > 0", name="ck_compound_policy"
        ),
        sa.CheckConstraint(
            "length(trim(rdkit_version)) > 0", name="ck_compound_rdkit_version"
        ),
        sa.CheckConstraint(
            "inchi_version IS NULL OR length(trim(inchi_version)) > 0",
            name="ck_compound_inchi_version",
        ),
        sa.CheckConstraint(
            _INCHI.format(column="inchikey"), name="ck_compound_inchikey"
        ),
        sa.CheckConstraint("created_at LIKE '%Z'", name="ck_compound_created_at_utc"),
    )
    op.create_index("ix_compound_structure_hash", "compound", ["structure_hash"])
    op.create_index("ix_compound_inchikey", "compound", ["inchikey"])

    op.create_table(
        "molecular_state",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("compound_id", sa.String(36), nullable=False),
        sa.Column("state_smiles", sa.Text(), nullable=False),
        sa.Column("state_inchikey", sa.String(27), nullable=True),
        sa.Column("formal_charge", sa.Integer(), nullable=False),
        sa.Column("stereochemistry_signature", sa.Text(), nullable=False),
        sa.Column("protonation_signature", sa.Text(), nullable=False),
        sa.Column("tautomer_signature", sa.Text(), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("chemistry_policy_id", sa.Text(), nullable=False),
        sa.Column("rdkit_version", sa.Text(), nullable=False),
        sa.Column("inchi_version", sa.Text(), nullable=True),
        sa.Column("preparation_ph", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_molecular_state"),
        sa.ForeignKeyConstraint(
            ["compound_id"],
            ["compound.id"],
            name="fk_molecular_state_compound",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("state_hash", name="uq_molecular_state_hash"),
        sa.CheckConstraint(
            "length(trim(state_smiles)) > 0", name="ck_molecular_state_smiles"
        ),
        sa.CheckConstraint(
            "length(trim(stereochemistry_signature)) > 0",
            name="ck_molecular_state_stereo",
        ),
        sa.CheckConstraint(
            "length(trim(protonation_signature)) > 0",
            name="ck_molecular_state_protonation",
        ),
        sa.CheckConstraint(
            "length(trim(tautomer_signature)) > 0", name="ck_molecular_state_tautomer"
        ),
        sa.CheckConstraint(
            "length(state_hash) = 64 AND state_hash = lower(state_hash) AND state_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_molecular_state_hash",
        ),
        sa.CheckConstraint(
            "length(trim(chemistry_policy_id)) > 0", name="ck_molecular_state_policy"
        ),
        sa.CheckConstraint(
            "length(trim(rdkit_version)) > 0", name="ck_molecular_state_rdkit_version"
        ),
        sa.CheckConstraint(
            "inchi_version IS NULL OR length(trim(inchi_version)) > 0",
            name="ck_molecular_state_inchi_version",
        ),
        sa.CheckConstraint(
            _INCHI.format(column="state_inchikey"), name="ck_molecular_state_inchikey"
        ),
        sa.CheckConstraint(
            "preparation_ph IS NULL OR (preparation_ph >= 0 AND preparation_ph <= 14)",
            name="ck_molecular_state_ph",
        ),
    )
    op.create_index(
        "ix_molecular_state_compound_id", "molecular_state", ["compound_id"]
    )
    op.create_index("ix_molecular_state_state_hash", "molecular_state", ["state_hash"])
    op.create_index(
        "ix_molecular_state_inchikey", "molecular_state", ["state_inchikey"]
    )

    op.create_table(
        "alias",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_value", sa.Text(), nullable=False),
        sa.Column("import_batch_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_alias"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batch.id"],
            name="fk_alias_import_batch",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_batch_id",
            "source_system",
            "source_value",
            name="uq_alias_batch_source",
        ),
        sa.CheckConstraint(
            "length(source_system) BETWEEN 1 AND 128 AND source_system NOT GLOB '*[^a-z0-9._-]*' AND substr(source_system, 1, 1) GLOB '[a-z0-9]'",
            name="ck_alias_source_system_format",
        ),
        sa.CheckConstraint(
            "length(source_value) BETWEEN 1 AND 1024 AND length(trim(source_value)) > 0 AND instr(source_value, char(0)) = 0",
            name="ck_alias_source_value_bounds",
        ),
        sa.CheckConstraint("created_at LIKE '%Z'", name="ck_alias_created_at_utc"),
    )
    op.create_index("ix_alias_import_batch_id", "alias", ["import_batch_id"])
    op.create_index("ix_alias_source", "alias", ["source_system", "source_value"])

    op.create_table(
        "identity_resolution",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("alias_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("compound_id", sa.String(36), nullable=True),
        sa.Column("molecular_state_id", sa.String(36), nullable=True),
        sa.Column("supersedes_id", sa.String(36), nullable=True),
        sa.Column("decided_at", sa.Text(), nullable=False),
        sa.Column("actor_kind", sa.String(10), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_identity_resolution"),
        sa.ForeignKeyConstraint(
            ["alias_id"],
            ["alias.id"],
            name="fk_identity_resolution_alias",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["compound_id"],
            ["compound.id"],
            name="fk_identity_resolution_compound",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["molecular_state_id"],
            ["molecular_state.id"],
            name="fk_identity_resolution_state",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["identity_resolution.id"],
            name="fk_identity_resolution_supersedes",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("supersedes_id", name="uq_identity_resolution_supersedes"),
        sa.CheckConstraint(
            "decision IN ('confirmed', 'reassigned', 'retracted', 'restored')",
            name="ck_identity_resolution_decision",
        ),
        sa.CheckConstraint(
            "(decision = 'confirmed' AND compound_id IS NOT NULL AND supersedes_id IS NULL) OR (decision = 'reassigned' AND compound_id IS NOT NULL AND supersedes_id IS NOT NULL) OR (decision = 'retracted' AND compound_id IS NULL AND molecular_state_id IS NULL AND supersedes_id IS NOT NULL) OR (decision = 'restored' AND compound_id IS NOT NULL AND supersedes_id IS NOT NULL AND actor_kind = 'user' AND rationale IS NOT NULL)",
            name="ck_identity_resolution_shape",
        ),
        sa.CheckConstraint(
            "actor_kind IN ('user', 'system')", name="ck_identity_resolution_actor_kind"
        ),
        sa.CheckConstraint(
            "(actor_kind = 'system' AND actor_id IS NULL) OR (actor_kind = 'user' AND length(trim(actor_id)) > 0)",
            name="ck_identity_resolution_actor",
        ),
        sa.CheckConstraint(
            "rationale IS NULL OR (length(trim(rationale)) > 0 AND length(rationale) <= 1024 AND instr(rationale, char(0)) = 0)",
            name="ck_identity_resolution_rationale",
        ),
        sa.CheckConstraint(
            "decided_at LIKE '%Z'", name="ck_identity_resolution_decided_at_utc"
        ),
    )
    op.create_index(
        "ix_identity_resolution_alias_id", "identity_resolution", ["alias_id"]
    )
    op.create_index(
        "ix_identity_resolution_compound_id", "identity_resolution", ["compound_id"]
    )
    op.create_index(
        "ix_identity_resolution_molecular_state_id",
        "identity_resolution",
        ["molecular_state_id"],
    )
    op.create_index(
        "uq_identity_resolution_alias_root",
        "identity_resolution",
        ["alias_id"],
        unique=True,
        sqlite_where=sa.text("supersedes_id IS NULL"),
    )

    _create_triggers()


def _create_triggers() -> None:
    op.execute("""
        CREATE TRIGGER trg_compound_no_update BEFORE UPDATE ON compound
        BEGIN SELECT RAISE(ABORT, 'compound rows are append-only'); END
    """)
    op.execute("""
        CREATE TRIGGER trg_compound_no_delete BEFORE DELETE ON compound
        BEGIN SELECT RAISE(ABORT, 'compound rows are append-only'); END
    """)
    op.execute("""
        CREATE TRIGGER trg_molecular_state_no_update BEFORE UPDATE ON molecular_state
        BEGIN SELECT RAISE(ABORT, 'molecular_state rows are append-only'); END
    """)
    op.execute("""
        CREATE TRIGGER trg_molecular_state_no_delete BEFORE DELETE ON molecular_state
        BEGIN SELECT RAISE(ABORT, 'molecular_state rows are append-only'); END
    """)
    op.execute("""
        CREATE TRIGGER trg_alias_no_update BEFORE UPDATE ON alias
        BEGIN SELECT RAISE(ABORT, 'alias rows are append-only'); END
    """)
    op.execute("""
        CREATE TRIGGER trg_alias_no_delete BEFORE DELETE ON alias
        BEGIN SELECT RAISE(ABORT, 'alias rows are append-only'); END
    """)
    op.execute("""
        CREATE TRIGGER trg_identity_resolution_no_update BEFORE UPDATE ON identity_resolution
        BEGIN SELECT RAISE(ABORT, 'identity_resolution rows are append-only'); END
    """)
    op.execute("""
        CREATE TRIGGER trg_identity_resolution_no_delete BEFORE DELETE ON identity_resolution
        BEGIN SELECT RAISE(ABORT, 'identity_resolution rows are append-only'); END
    """)
    op.execute("""
        CREATE TRIGGER trg_identity_resolution_validate_insert
        BEFORE INSERT ON identity_resolution
        BEGIN
            SELECT RAISE(ABORT, 'identity resolution root must be confirmed')
              WHERE NEW.supersedes_id IS NULL AND NEW.decision <> 'confirmed';
            SELECT RAISE(ABORT, 'identity resolution predecessor alias mismatch')
              WHERE NEW.supersedes_id IS NOT NULL AND NOT EXISTS
                (SELECT 1 FROM identity_resolution p WHERE p.id = NEW.supersedes_id AND p.alias_id = NEW.alias_id);
            SELECT RAISE(ABORT, 'identity resolution predecessor already has successor')
              WHERE NEW.supersedes_id IS NOT NULL AND EXISTS
                (SELECT 1 FROM identity_resolution s WHERE s.supersedes_id = NEW.supersedes_id);
            SELECT RAISE(ABORT, 'identity resolution state ownership mismatch')
              WHERE NEW.molecular_state_id IS NOT NULL AND NOT EXISTS
                (SELECT 1 FROM molecular_state s WHERE s.id = NEW.molecular_state_id AND s.compound_id = NEW.compound_id);
            SELECT RAISE(ABORT, 'identity resolution transition is invalid')
              WHERE NEW.decision IN ('reassigned', 'retracted') AND NEW.supersedes_id IS NOT NULL AND NOT EXISTS
                (SELECT 1 FROM identity_resolution p WHERE p.id = NEW.supersedes_id AND p.decision IN ('confirmed', 'reassigned', 'restored'));
            SELECT RAISE(ABORT, 'identity resolution restore is invalid')
              WHERE NEW.decision = 'restored' AND NOT EXISTS
                (SELECT 1 FROM identity_resolution p WHERE p.id = NEW.supersedes_id AND p.decision = 'retracted');
        END
    """)


def downgrade() -> None:  # pragma: no cover
    op.execute("DROP TRIGGER IF EXISTS trg_identity_resolution_validate_insert")
    op.execute("DROP TRIGGER IF EXISTS trg_identity_resolution_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_identity_resolution_no_update")
    op.execute("DROP TRIGGER IF EXISTS trg_alias_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_alias_no_update")
    op.execute("DROP TRIGGER IF EXISTS trg_molecular_state_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_molecular_state_no_update")
    op.execute("DROP TRIGGER IF EXISTS trg_compound_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_compound_no_update")
    op.drop_index("uq_identity_resolution_alias_root", table_name="identity_resolution")
    op.drop_index(
        "ix_identity_resolution_molecular_state_id", table_name="identity_resolution"
    )
    op.drop_index(
        "ix_identity_resolution_compound_id", table_name="identity_resolution"
    )
    op.drop_index("ix_identity_resolution_alias_id", table_name="identity_resolution")
    op.drop_table("identity_resolution")
    op.drop_index("ix_alias_source", table_name="alias")
    op.drop_index("ix_alias_import_batch_id", table_name="alias")
    op.drop_table("alias")
    op.drop_index("ix_molecular_state_inchikey", table_name="molecular_state")
    op.drop_index("ix_molecular_state_state_hash", table_name="molecular_state")
    op.drop_index("ix_molecular_state_compound_id", table_name="molecular_state")
    op.drop_table("molecular_state")
    op.drop_index("ix_compound_inchikey", table_name="compound")
    op.drop_index("ix_compound_structure_hash", table_name="compound")
    op.drop_table("compound")
