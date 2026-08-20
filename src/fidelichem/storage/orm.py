"""Private SQLAlchemy rows for the Phase 1 storage schema."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
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
    completed_at: Mapped[datetime | None] = mapped_column(
        UtcTimestamp(), nullable=True
    )
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
