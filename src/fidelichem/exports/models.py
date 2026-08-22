"""Domain models for audited scientific exports, manifests, and reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from fidelichem.domain.models import DomainModel


def _non_blank(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Field must not be empty or whitespace")
    return value.strip()


class ExportFormat(StrEnum):
    """Supported serialized export formats."""

    CSV = "csv"
    XLSX = "xlsx"
    PARQUET = "parquet"
    JSON = "json"
    METHODS_REPORT = "methods_report"


class ExportOptions(DomainModel):
    """Configuration options governing export bundle contents and formats."""

    formats: tuple[ExportFormat, ...] = Field(
        default=(ExportFormat.CSV, ExportFormat.JSON, ExportFormat.METHODS_REPORT)
    )
    include_scores: bool = True
    include_interactions: bool = True
    include_dynamics: bool = True
    include_provenance: bool = True
    include_decisions: bool = True


class FileHashRecord(DomainModel):
    """Cryptographic hash record for a generated export artifact."""

    file_name: str
    relative_path: str
    sha256: str
    size_bytes: int = Field(ge=0, strict=True)

    _file_name_not_blank = field_validator("file_name")(_non_blank)
    _sha256_not_blank = field_validator("sha256")(_non_blank)


class ExportManifest(DomainModel):
    """Audit and reproducibility manifest accompanying exported scientific data."""

    manifest_version: str = "1.0"
    project_name: str
    fidelichem_version: str
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    exported_files: tuple[FileHashRecord, ...] = Field(default_factory=tuple)
    summary_counts: Mapping[str, int] = Field(default_factory=dict)
    parameters: Mapping[str, Any] = Field(default_factory=dict)

    _project_name_not_blank = field_validator("project_name")(_non_blank)


class ExportResult(DomainModel):
    """Result of an export operation containing manifest and generated files."""

    manifest_path: str
    files: Sequence[str] = Field(default_factory=tuple)
    total_records: int = Field(ge=0, strict=True)
    manifest: ExportManifest


__all__ = [
    "ExportFormat",
    "ExportManifest",
    "ExportOptions",
    "ExportResult",
    "FileHashRecord",
]
