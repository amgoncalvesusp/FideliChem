"""Private SQLAlchemy rows for the Phase 1 storage schema."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    """Declarative metadata for migration autogeneration and row mappings."""


class UtcTimestamp(TypeDecorator[datetime]):
    """Persist an aware UTC datetime as an explicit ISO-8601 UTC string."""

    impl = Text()
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: object,
    ) -> str | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        normalized = value.astimezone(UTC)
        return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")

    def process_result_value(
        self,
        value: str | None,
        dialect: object,
    ) -> datetime | None:
        del dialect
        if value is None:
            return None
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
        return parsed.astimezone(UTC)


class _ProjectRow(Base):
    __tablename__ = "project"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_project_name_nonblank",
        ),
        CheckConstraint(
            "schema_version >= 1",
            name="ck_project_schema_version_positive",
        ),
        CheckConstraint("created_at LIKE '%Z'", name="ck_project_created_at_utc"),
        CheckConstraint("updated_at LIKE '%Z'", name="ck_project_updated_at_utc"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcTimestamp())
    updated_at: Mapped[datetime] = mapped_column(UtcTimestamp())
    schema_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
    )


class _ImportBatchRow(Base):
    __tablename__ = "import_batch"
    __table_args__ = (
        Index("ix_import_batch_project_id", "project_id"),
        Index("ix_import_batch_adapter_id", "adapter_id"),
        Index("ix_import_batch_input_hash", "input_hash"),
        CheckConstraint(
            "status IN ('in_progress', 'completed', 'failed', 'rolled_back')",
            name="ck_import_batch_status",
        ),
        CheckConstraint(
            "length(trim(adapter_id)) > 0",
            name="ck_batch_adapter_id",
        ),
        CheckConstraint(
            "length(trim(adapter_version)) > 0",
            name="ck_batch_adapter_version",
        ),
        CheckConstraint(
            "length(trim(source_root)) > 0",
            name="ck_batch_source_root",
        ),
        CheckConstraint("file_count >= 0", name="ck_batch_file_count"),
        CheckConstraint("started_at LIKE '%Z'", name="ck_batch_started_at_utc"),
        CheckConstraint(
            "completed_at IS NULL OR completed_at LIKE '%Z'",
            name="ck_batch_completed_at_utc",
        ),
        CheckConstraint(
            "rolled_back_at IS NULL OR rolled_back_at LIKE '%Z'",
            name="ck_batch_rolled_back_at_utc",
        ),
        CheckConstraint(
            "input_hash IS NULL OR (length(input_hash) = 64 AND "
            "input_hash = lower(input_hash) AND input_hash NOT GLOB '*[^0-9a-f]*')",
            name="ck_batch_input_hash",
        ),
        CheckConstraint("json_valid(warnings_json)", name="ck_batch_warnings_json"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project.id", name="fk_import_batch_project", ondelete="RESTRICT"),
    )
    adapter_id: Mapped[str] = mapped_column(Text)
    adapter_version: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(UtcTimestamp())
    completed_at: Mapped[datetime | None] = mapped_column(UtcTimestamp(), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default="in_progress",
        server_default=text("'in_progress'"),
    )
    source_root: Mapped[str] = mapped_column(Text)
    file_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
    )
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    warnings_json: Mapped[str] = mapped_column(
        Text,
        default="[]",
        server_default=text("'[]'"),
    )
    rolled_back_at: Mapped[datetime | None] = mapped_column(
        UtcTimestamp(), nullable=True
    )
    rollback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class _SourceArtifactRow(Base):
    __tablename__ = "source_artifact"
    __table_args__ = (
        Index("ix_source_artifact_import_batch_id", "import_batch_id"),
        Index("ix_source_artifact_sha256", "sha256"),
        UniqueConstraint(
            "import_batch_id",
            "relative_path",
            name="uq_source_artifact_batch_relative_path",
        ),
        CheckConstraint("length(trim(path)) > 0", name="ck_artifact_path"),
        CheckConstraint(
            "length(trim(relative_path)) > 0",
            name="ck_artifact_relative_path",
        ),
        CheckConstraint(
            "length(trim(relative_path)) > 0 AND "
            "instr(relative_path, char(0)) = 0 AND "
            "instr(relative_path, char(92)) = 0 AND "
            "substr(relative_path, 1, 1) <> '/' AND "
            "relative_path NOT GLOB '[A-Za-z]:*' AND "
            "relative_path <> '..' AND "
            "relative_path NOT LIKE '../%' AND "
            "relative_path NOT LIKE '%/../%' AND "
            "relative_path NOT LIKE '%/..' AND "
            "relative_path <> '.' AND "
            "relative_path NOT LIKE './%' AND "
            "relative_path NOT LIKE '%/./%' AND "
            "relative_path NOT LIKE '%/.' AND "
            "relative_path NOT LIKE '%//%' AND "
            "relative_path NOT LIKE '%/'",
            name="ck_artifact_relative_path_safe",
        ),
        CheckConstraint(
            "length(sha256) = 64 AND sha256 = lower(sha256) AND "
            "sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_artifact_sha256",
        ),
        CheckConstraint(
            "length(trim(file_type)) > 0",
            name="ck_artifact_file_type",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_artifact_size_bytes"),
        CheckConstraint("mtime LIKE '%Z'", name="ck_artifact_mtime_utc"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "import_batch.id",
            name="fk_source_artifact_import_batch",
            ondelete="RESTRICT",
        ),
    )
    path: Mapped[str] = mapped_column(Text)
    relative_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    file_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    mtime: Mapped[datetime] = mapped_column(UtcTimestamp())


class _AuditEventRow(Base):
    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_event_import_batch_id", "import_batch_id"),
        Index("ix_audit_event_entity", "entity_type", "entity_id"),
        Index("ix_audit_event_sequence", "sequence"),
        UniqueConstraint("sequence", name="uq_audit_event_sequence"),
        CheckConstraint("length(trim(action)) > 0", name="ck_audit_action"),
        CheckConstraint(
            "length(trim(entity_type)) > 0",
            name="ck_audit_entity_type",
        ),
        CheckConstraint("length(trim(entity_id)) > 0", name="ck_audit_entity_id"),
        CheckConstraint("length(trim(source)) > 0", name="ck_audit_source"),
        CheckConstraint(
            "actor_kind IN ('user', 'system')",
            name="ck_audit_actor_kind",
        ),
        CheckConstraint("timestamp LIKE '%Z'", name="ck_audit_timestamp_utc"),
        CheckConstraint(
            "old_value_json IS NULL OR json_valid(old_value_json)",
            name="ck_audit_old_json",
        ),
        CheckConstraint(
            "new_value_json IS NULL OR json_valid(new_value_json)",
            name="ck_audit_new_json",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UtcTimestamp())
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str] = mapped_column(Text)
    import_batch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "import_batch.id",
            name="fk_audit_event_import_batch",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    old_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text)
    actor_kind: Mapped[str] = mapped_column(
        String(10),
        default="system",
        server_default=text("'system'"),
    )
    actor_id: Mapped[str | None] = mapped_column(Text, nullable=True)


_INCHI_CHECK = (
    "{column} IS NULL OR (length({column}) = 27 AND "
    "substr({column}, 15, 1) = '-' AND substr({column}, 26, 1) = '-' AND "
    "substr({column}, 1, 14) NOT GLOB '*[^A-Z]*' AND "
    "substr({column}, 16, 10) NOT GLOB '*[^A-Z]*' AND "
    "substr({column}, 27, 1) GLOB '[A-Z]')"
)
_SQL_STRIP_CHARS = (
    "char(9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,"
    "8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288)"
)


def _sql_nonblank(column: str) -> str:
    return f"length(trim({column}, {_SQL_STRIP_CHARS})) > 0"


class _CompoundRow(Base):
    __tablename__ = "compound"
    __table_args__ = (
        Index("ix_compound_structure_hash", "structure_hash"),
        Index("ix_compound_inchikey", "inchikey"),
        UniqueConstraint("structure_hash", name="uq_compound_structure_hash"),
        CheckConstraint(
            _sql_nonblank("canonical_smiles"), name="ck_compound_canonical_smiles"
        ),
        CheckConstraint(
            _sql_nonblank("isomeric_smiles"), name="ck_compound_isomeric_smiles"
        ),
        CheckConstraint(_sql_nonblank("formula"), name="ck_compound_formula"),
        CheckConstraint(
            "molecular_weight > 0 AND molecular_weight <= 1.7976931348623157e308",
            name="ck_compound_molecular_weight",
        ),
        CheckConstraint(
            "length(structure_hash) = 64 AND structure_hash = lower(structure_hash) "
            "AND structure_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_compound_structure_hash",
        ),
        CheckConstraint(
            _sql_nonblank("chemistry_policy_id"), name="ck_compound_policy"
        ),
        CheckConstraint(
            _sql_nonblank("rdkit_version"), name="ck_compound_rdkit_version"
        ),
        CheckConstraint(
            f"inchi_version IS NULL OR {_sql_nonblank('inchi_version')}",
            name="ck_compound_inchi_version",
        ),
        CheckConstraint(
            _INCHI_CHECK.format(column="inchikey"), name="ck_compound_inchikey"
        ),
        CheckConstraint("created_at LIKE '%Z'", name="ck_compound_created_at_utc"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_smiles: Mapped[str] = mapped_column(Text)
    isomeric_smiles: Mapped[str] = mapped_column(Text)
    inchikey: Mapped[str | None] = mapped_column(String(27), nullable=True)
    formula: Mapped[str] = mapped_column(Text)
    molecular_weight: Mapped[float] = mapped_column(Float)
    structure_hash: Mapped[str] = mapped_column(String(64))
    chemistry_policy_id: Mapped[str] = mapped_column(Text)
    rdkit_version: Mapped[str] = mapped_column(Text)
    inchi_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcTimestamp())


class _MolecularStateRow(Base):
    __tablename__ = "molecular_state"
    __table_args__ = (
        Index("ix_molecular_state_compound_id", "compound_id"),
        Index("ix_molecular_state_state_hash", "state_hash"),
        Index("ix_molecular_state_inchikey", "state_inchikey"),
        UniqueConstraint("state_hash", name="uq_molecular_state_hash"),
        CheckConstraint(
            _sql_nonblank("state_smiles"), name="ck_molecular_state_smiles"
        ),
        CheckConstraint(
            _sql_nonblank("stereochemistry_signature"),
            name="ck_molecular_state_stereo",
        ),
        CheckConstraint(
            _sql_nonblank("protonation_signature"),
            name="ck_molecular_state_protonation",
        ),
        CheckConstraint(
            _sql_nonblank("tautomer_signature"), name="ck_molecular_state_tautomer"
        ),
        CheckConstraint(
            "length(state_hash) = 64 AND state_hash = lower(state_hash) "
            "AND state_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_molecular_state_hash",
        ),
        CheckConstraint(
            _sql_nonblank("chemistry_policy_id"), name="ck_molecular_state_policy"
        ),
        CheckConstraint(
            _sql_nonblank("rdkit_version"), name="ck_molecular_state_rdkit_version"
        ),
        CheckConstraint(
            f"inchi_version IS NULL OR {_sql_nonblank('inchi_version')}",
            name="ck_molecular_state_inchi_version",
        ),
        CheckConstraint(
            _INCHI_CHECK.format(column="state_inchikey"),
            name="ck_molecular_state_inchikey",
        ),
        CheckConstraint(
            "preparation_ph IS NULL OR (preparation_ph >= 0 AND preparation_ph <= 14)",
            name="ck_molecular_state_ph",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    compound_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "compound.id", name="fk_molecular_state_compound", ondelete="RESTRICT"
        ),
    )
    state_smiles: Mapped[str] = mapped_column(Text)
    state_inchikey: Mapped[str | None] = mapped_column(String(27), nullable=True)
    formal_charge: Mapped[int] = mapped_column(Integer)
    stereochemistry_signature: Mapped[str] = mapped_column(Text)
    protonation_signature: Mapped[str] = mapped_column(Text)
    tautomer_signature: Mapped[str] = mapped_column(Text)
    state_hash: Mapped[str] = mapped_column(String(64))
    chemistry_policy_id: Mapped[str] = mapped_column(Text)
    rdkit_version: Mapped[str] = mapped_column(Text)
    inchi_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    preparation_ph: Mapped[float | None] = mapped_column(Float, nullable=True)


class _AliasRow(Base):
    __tablename__ = "alias"
    __table_args__ = (
        Index("ix_alias_import_batch_id", "import_batch_id"),
        Index("ix_alias_source", "source_system", "source_value"),
        UniqueConstraint(
            "import_batch_id",
            "source_system",
            "source_value",
            name="uq_alias_batch_source",
        ),
        CheckConstraint(
            "length(source_system) BETWEEN 1 AND 128 AND "
            "instr(source_system, char(0)) = 0 AND "
            "source_system NOT GLOB '*[^a-z0-9._-]*' AND "
            "substr(source_system, 1, 1) GLOB '[a-z0-9]'",
            name="ck_alias_source_system_format",
        ),
        CheckConstraint(
            f"length(source_value) BETWEEN 1 AND 1024 AND "
            f"{_sql_nonblank('source_value')} AND "
            "instr(source_value, char(0)) = 0",
            name="ck_alias_source_value_bounds",
        ),
        CheckConstraint("created_at LIKE '%Z'", name="ck_alias_created_at_utc"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_system: Mapped[str] = mapped_column(Text)
    source_value: Mapped[str] = mapped_column(Text)
    import_batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "import_batch.id", name="fk_alias_import_batch", ondelete="RESTRICT"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(UtcTimestamp())


class _IdentityResolutionRow(Base):
    __tablename__ = "identity_resolution"
    __table_args__ = (
        Index(
            "uq_identity_resolution_alias_root",
            "alias_id",
            unique=True,
            sqlite_where=text("supersedes_id IS NULL"),
        ),
        Index("ix_identity_resolution_alias_id", "alias_id"),
        Index("ix_identity_resolution_compound_id", "compound_id"),
        Index("ix_identity_resolution_molecular_state_id", "molecular_state_id"),
        UniqueConstraint("supersedes_id", name="uq_identity_resolution_supersedes"),
        CheckConstraint(
            "decision IN ('confirmed', 'reassigned', 'retracted', 'restored')",
            name="ck_identity_resolution_decision",
        ),
        CheckConstraint(
            "decision IS NOT NULL AND actor_kind IS NOT NULL AND ("
            "(decision = 'confirmed' AND compound_id IS NOT NULL AND "
            "supersedes_id IS NULL) OR "
            "(decision = 'reassigned' AND compound_id IS NOT NULL AND "
            "supersedes_id IS NOT NULL) OR "
            "(decision = 'retracted' AND compound_id IS NULL AND "
            "molecular_state_id IS NULL AND supersedes_id IS NOT NULL) OR "
            "(decision = 'restored' AND compound_id IS NOT NULL AND "
            "supersedes_id IS NOT NULL AND actor_kind = 'user' AND "
            "rationale IS NOT NULL))",
            name="ck_identity_resolution_shape",
        ),
        CheckConstraint(
            "actor_kind IN ('user', 'system')", name="ck_identity_resolution_actor_kind"
        ),
        CheckConstraint(
            "(actor_kind = 'system' AND actor_id IS NULL) OR "
            "(actor_kind = 'user' AND actor_id IS NOT NULL AND "
            f"{_sql_nonblank('actor_id')} AND length(actor_id) <= 128 AND "
            "instr(actor_id, char(0)) = 0)",
            name="ck_identity_resolution_actor",
        ),
        CheckConstraint(
            "rationale IS NULL OR ("
            f"{_sql_nonblank('rationale')} AND length(rationale) <= 1024 AND "
            "instr(rationale, char(0)) = 0)",
            name="ck_identity_resolution_rationale",
        ),
        CheckConstraint(
            "decided_at LIKE '%Z'", name="ck_identity_resolution_decided_at_utc"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alias_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "alias.id", name="fk_identity_resolution_alias", ondelete="RESTRICT"
        ),
    )
    decision: Mapped[str] = mapped_column(String(20))
    compound_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "compound.id", name="fk_identity_resolution_compound", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    molecular_state_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "molecular_state.id",
            name="fk_identity_resolution_state",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    supersedes_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "identity_resolution.id",
            name="fk_identity_resolution_supersedes",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    decided_at: Mapped[datetime] = mapped_column(UtcTimestamp())
    actor_kind: Mapped[str] = mapped_column(String(10))
    actor_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)


class _EvidenceTargetRow(Base):
    """Immutable imported target evidence and its provenance edge."""

    __tablename__ = "evidence_target"
    __table_args__ = (
        Index("ix_evidence_target_import_batch_id", "import_batch_id"),
        UniqueConstraint(
            "import_batch_id", "name", name="uq_evidence_target_batch_name"
        ),
        CheckConstraint(_sql_nonblank("name"), name="ck_evidence_target_name"),
        CheckConstraint(
            "sequence_hash IS NULL OR (length(sequence_hash) = 64 AND "
            "sequence_hash = lower(sequence_hash) AND "
            "sequence_hash NOT GLOB '*[^0-9a-f]*')",
            name="ck_evidence_target_sequence_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "import_batch.id", name="fk_evidence_target_batch", ondelete="RESTRICT"
        ),
    )
    source_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "source_artifact.id",
            name="fk_evidence_target_artifact",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text)
    accession: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdb_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    chain: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class _DockingRunRow(Base):
    """Immutable docking run evidence with parent target and provenance."""

    __tablename__ = "docking_run"
    __table_args__ = (
        Index("ix_docking_run_import_batch_id", "import_batch_id"),
        UniqueConstraint(
            "import_batch_id", "run_name", name="uq_docking_run_batch_name"
        ),
        CheckConstraint(_sql_nonblank("run_name"), name="ck_docking_run_name"),
        CheckConstraint(_sql_nonblank("engine"), name="ck_docking_run_engine"),
        CheckConstraint(
            "configuration_hash IS NULL OR (length(configuration_hash) = 64 AND "
            "configuration_hash = lower(configuration_hash) AND "
            "configuration_hash NOT GLOB '*[^0-9a-f]*')",
            name="ck_docking_run_config_hash",
        ),
        CheckConstraint(
            "json_valid(parameters_json)", name="ck_docking_run_parameters_json"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("import_batch.id", name="fk_docking_run_batch", ondelete="RESTRICT"),
    )
    source_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "source_artifact.id", name="fk_docking_run_artifact", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    target_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "evidence_target.id", name="fk_docking_run_target", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    run_name: Mapped[str] = mapped_column(Text)
    target_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine: Mapped[str] = mapped_column(Text)
    engine_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    configuration_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameters_json: Mapped[str] = mapped_column(
        Text, default="{}", server_default=text("'{}'")
    )


class _PoseRow(Base):
    """Immutable docking pose evidence."""

    __tablename__ = "pose"
    __table_args__ = (
        Index("ix_pose_import_batch_id", "import_batch_id"),
        Index("ix_pose_docking_run_id", "docking_run_id"),
        UniqueConstraint(
            "docking_run_id", "source_pose_id", name="uq_pose_run_source_id"
        ),
        CheckConstraint(_sql_nonblank("run_name"), name="ck_pose_run_name"),
        CheckConstraint(
            _sql_nonblank("compound_source_system"), name="ck_pose_source_system"
        ),
        CheckConstraint(
            _sql_nonblank("compound_source_value"), name="ck_pose_source_value"
        ),
        CheckConstraint(_sql_nonblank("source_pose_id"), name="ck_pose_source_id"),
        CheckConstraint("rank >= 1", name="ck_pose_rank"),
        CheckConstraint(
            "coordinate_hash IS NULL OR (length(coordinate_hash) = 64 AND "
            "coordinate_hash = lower(coordinate_hash) AND "
            "coordinate_hash NOT GLOB '*[^0-9a-f]*')",
            name="ck_pose_coordinate_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("import_batch.id", name="fk_pose_batch", ondelete="RESTRICT"),
    )
    source_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("source_artifact.id", name="fk_pose_artifact", ondelete="RESTRICT"),
        nullable=True,
    )
    docking_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("docking_run.id", name="fk_pose_docking_run", ondelete="RESTRICT"),
    )
    run_name: Mapped[str] = mapped_column(Text)
    compound_source_system: Mapped[str] = mapped_column(Text)
    compound_source_value: Mapped[str] = mapped_column(Text)
    source_pose_id: Mapped[str] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer)
    structure_artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    coordinate_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class _ScoreObservationRow(Base):
    """Immutable score observation linked to a docking run and optional pose."""

    __tablename__ = "score_observation"
    __table_args__ = (
        Index("ix_score_observation_import_batch_id", "import_batch_id"),
        Index("ix_score_observation_docking_run_id", "docking_run_id"),
        UniqueConstraint(
            "docking_run_id",
            "source_pose_id",
            "score_key",
            name="uq_score_run_pose_key",
        ),
        CheckConstraint(_sql_nonblank("run_name"), name="ck_score_run_name"),
        CheckConstraint(
            _sql_nonblank("compound_source_value"), name="ck_score_source_value"
        ),
        CheckConstraint(
            _sql_nonblank("source_pose_id"), name="ck_score_source_pose_id"
        ),
        CheckConstraint(_sql_nonblank("score_key"), name="ck_score_key"),
        CheckConstraint(
            "raw_value = raw_value AND abs(raw_value) <= 1.7976931348623157e308",
            name="ck_score_finite",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("import_batch.id", name="fk_score_batch", ondelete="RESTRICT"),
    )
    source_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("source_artifact.id", name="fk_score_artifact", ondelete="RESTRICT"),
        nullable=True,
    )
    docking_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("docking_run.id", name="fk_score_docking_run", ondelete="RESTRICT"),
    )
    pose_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("pose.id", name="fk_score_pose", ondelete="RESTRICT"),
        nullable=True,
    )
    run_name: Mapped[str] = mapped_column(Text)
    compound_source_value: Mapped[str] = mapped_column(Text)
    source_pose_id: Mapped[str] = mapped_column(Text)
    score_key: Mapped[str] = mapped_column(Text)
    raw_value: Mapped[float] = mapped_column(Float)
    source_artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class _InteractionRow(Base):
    """Immutable interaction evidence linked to optional pose/run/target parents."""

    __tablename__ = "interaction"
    __table_args__ = (
        Index("ix_interaction_import_batch_id", "import_batch_id"),
        Index("ix_interaction_pose_id", "pose_id"),
        CheckConstraint(_sql_nonblank("run_name"), name="ck_interaction_run_name"),
        CheckConstraint(
            _sql_nonblank("compound_source_value"), name="ck_interaction_source_value"
        ),
        CheckConstraint(
            _sql_nonblank("source_pose_id"), name="ck_interaction_source_pose_id"
        ),
        CheckConstraint(
            _sql_nonblank("residue_name"), name="ck_interaction_residue_name"
        ),
        CheckConstraint(_sql_nonblank("interaction_type"), name="ck_interaction_type"),
        CheckConstraint(
            "json_valid(metadata_json)", name="ck_interaction_metadata_json"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("import_batch.id", name="fk_interaction_batch", ondelete="RESTRICT"),
    )
    source_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "source_artifact.id", name="fk_interaction_artifact", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    docking_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "docking_run.id", name="fk_interaction_docking_run", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    pose_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("pose.id", name="fk_interaction_pose", ondelete="RESTRICT"),
        nullable=True,
    )
    target_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "evidence_target.id", name="fk_interaction_target", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    run_name: Mapped[str] = mapped_column(Text)
    compound_source_value: Mapped[str] = mapped_column(Text)
    source_pose_id: Mapped[str] = mapped_column(Text)
    residue_name: Mapped[str] = mapped_column(Text)
    interaction_type: Mapped[str] = mapped_column(Text)
    target_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    residue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chain: Mapped[str | None] = mapped_column(Text, nullable=True)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    angle: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy: Mapped[float | None] = mapped_column(Float, nullable=True)
    frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    ligand_feature: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(
        Text, default="{}", server_default=text("'{}'")
    )


class _MDRunRow(Base):
    """Immutable molecular dynamics run evidence."""

    __tablename__ = "md_run"
    __table_args__ = (
        Index("ix_md_run_import_batch_id", "import_batch_id"),
        UniqueConstraint("import_batch_id", "run_name", name="uq_md_run_batch_name"),
        CheckConstraint(_sql_nonblank("run_name"), name="ck_md_run_name"),
        CheckConstraint(_sql_nonblank("engine"), name="ck_md_run_engine"),
        CheckConstraint(
            "duration_ns IS NULL OR (duration_ns = duration_ns AND "
            "abs(duration_ns) <= 1.7976931348623157e308)",
            name="ck_md_run_duration_finite",
        ),
        CheckConstraint(
            "temperature_k IS NULL OR (temperature_k = temperature_k AND "
            "abs(temperature_k) <= 1.7976931348623157e308)",
            name="ck_md_run_temperature_finite",
        ),
        CheckConstraint(
            "timestep_fs IS NULL OR (timestep_fs = timestep_fs AND "
            "abs(timestep_fs) <= 1.7976931348623157e308)",
            name="ck_md_run_timestep_finite",
        ),
        CheckConstraint(
            "json_valid(parameters_json)", name="ck_md_run_parameters_json"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("import_batch.id", name="fk_md_run_batch", ondelete="RESTRICT"),
    )
    source_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "source_artifact.id", name="fk_md_run_artifact", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    target_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("evidence_target.id", name="fk_md_run_target", ondelete="RESTRICT"),
        nullable=True,
    )
    pose_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("pose.id", name="fk_md_run_pose", ondelete="RESTRICT"),
        nullable=True,
    )
    run_name: Mapped[str] = mapped_column(Text)
    target_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    compound_source_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_pose_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ns: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestep_fs: Mapped[float | None] = mapped_column(Float, nullable=True)
    engine: Mapped[str] = mapped_column(Text)
    engine_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters_json: Mapped[str] = mapped_column(
        Text, default="{}", server_default=text("'{}'")
    )


class _MDMetricRow(Base):
    """Immutable molecular dynamics metric summary and time series."""

    __tablename__ = "md_metric"
    __table_args__ = (
        Index("ix_md_metric_import_batch_id", "import_batch_id"),
        Index("ix_md_metric_md_run_id", "md_run_id"),
        UniqueConstraint("md_run_id", "metric_key", name="uq_md_metric_run_key"),
        CheckConstraint(_sql_nonblank("run_name"), name="ck_md_metric_run_name"),
        CheckConstraint(_sql_nonblank("metric_key"), name="ck_md_metric_key"),
        CheckConstraint(
            "json_valid(time_points_json)", name="ck_md_metric_time_points_json"
        ),
        CheckConstraint("json_valid(values_json)", name="ck_md_metric_values_json"),
        CheckConstraint("json_valid(metadata_json)", name="ck_md_metric_metadata_json"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("import_batch.id", name="fk_md_metric_batch", ondelete="RESTRICT"),
    )
    source_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "source_artifact.id", name="fk_md_metric_artifact", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    md_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("md_run.id", name="fk_md_metric_run", ondelete="RESTRICT"),
    )
    run_name: Mapped[str] = mapped_column(Text)
    metric_key: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    mean_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    std_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    compound_source_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_pose_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_points_json: Mapped[str] = mapped_column(
        Text, default="[]", server_default=text("'[]'")
    )
    values_json: Mapped[str] = mapped_column(
        Text, default="[]", server_default=text("'[]'")
    )
    metadata_json: Mapped[str] = mapped_column(
        Text, default="{}", server_default=text("'{}'")
    )
