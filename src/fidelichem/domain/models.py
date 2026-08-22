"""Immutable domain values for the Phase 1 storage boundary."""

from __future__ import annotations

import posixpath
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
)

from .errors import InvalidHashError, InvalidTimestampError, UnsafePathError
from .ids import new_id, validate_id
from .json import canonicalize_json_text


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidTimestampError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


def _sha256(value: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise InvalidHashError("sha256 must be 64 lowercase hexadecimal characters")
    return value


def _safe_relative_path(value: str) -> str:
    if not value or "\x00" in value or "\\" in value:
        raise UnsafePathError("relative_path must be a safe POSIX path")
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if posix_path.is_absolute() or windows_path.drive:
        raise UnsafePathError("relative_path must be relative")
    parts = value.split("/")
    if ".." in parts:
        raise UnsafePathError("relative_path must not contain '..'")
    normalized = posixpath.normpath(value)
    if normalized in ("", ".", "..") or normalized.startswith("../"):
        raise UnsafePathError("relative_path must identify a file")
    return normalized


def _json_text(value: str | None) -> str | None:
    if value is None:
        return None
    return canonicalize_json_text(value)


OpaqueId = Annotated[str, BeforeValidator(validate_id)]
UtcTimestamp = Annotated[datetime, AfterValidator(_utc)]
Sha256Digest = Annotated[str, AfterValidator(_sha256)]
SafeRelativePath = Annotated[str, AfterValidator(_safe_relative_path)]


class DomainModel(BaseModel):
    """Shared immutable Pydantic configuration for public values."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_default=True,
        validate_assignment=True,
    )


class ImportStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ActorKind(StrEnum):
    USER = "user"
    SYSTEM = "system"


class Project(DomainModel):
    id: OpaqueId = Field(default_factory=new_id)
    name: str
    description: str | None = None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    schema_version: int = Field(default=1, ge=1, strict=True)

    _name_not_blank = field_validator("name")(_non_blank)


class ImportBatch(DomainModel):
    id: OpaqueId = Field(default_factory=new_id)
    project_id: OpaqueId
    adapter_id: str
    adapter_version: str
    started_at: UtcTimestamp
    completed_at: UtcTimestamp | None = None
    status: ImportStatus = ImportStatus.IN_PROGRESS
    source_root: str
    file_count: int = Field(default=0, ge=0, strict=True)
    input_hash: Sha256Digest | None = None
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    rolled_back_at: UtcTimestamp | None = None
    rollback_reason: str | None = None

    _adapter_id_not_blank = field_validator("adapter_id")(_non_blank)
    _adapter_version_not_blank = field_validator("adapter_version")(_non_blank)
    _source_root_not_blank = field_validator("source_root")(_non_blank)


class SourceArtifact(DomainModel):
    id: OpaqueId = Field(default_factory=new_id)
    import_batch_id: OpaqueId
    path: str
    relative_path: SafeRelativePath
    sha256: Sha256Digest
    file_type: str
    size_bytes: int = Field(ge=0, strict=True)
    mtime: UtcTimestamp

    _path_not_blank = field_validator("path")(_non_blank)
    _file_type_not_blank = field_validator("file_type")(_non_blank)


class AuditEvent(DomainModel):
    id: OpaqueId = Field(default_factory=new_id)
    sequence: int | None = Field(default=None, ge=0, strict=True)
    timestamp: UtcTimestamp
    action: str
    entity_type: str
    entity_id: str
    import_batch_id: OpaqueId | None = None
    old_value_json: str | None = None
    new_value_json: str | None = None
    source: str
    actor_kind: ActorKind = ActorKind.SYSTEM
    actor_id: str | None = None

    _action_not_blank = field_validator("action")(_non_blank)
    _entity_type_not_blank = field_validator("entity_type")(_non_blank)
    _entity_id_not_blank = field_validator("entity_id")(_non_blank)
    _source_not_blank = field_validator("source")(_non_blank)
    _old_value_json = field_validator("old_value_json", "new_value_json")(_json_text)
