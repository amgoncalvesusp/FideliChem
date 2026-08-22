"""Cryptographic manifest generator for export packages."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fidelichem

from .models import ExportManifest, FileHashRecord


def _compute_sha256(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def create_export_manifest(
    project_name: str,
    export_files: Sequence[Path],
    export_root: Path,
    summary_counts: Mapping[str, int] | None = None,
    parameters: Mapping[str, Any] | None = None,
) -> ExportManifest:
    """Generate an ExportManifest with SHA-256 digests for all files."""
    version = getattr(fidelichem, "__version__", "0.1.0")
    file_records: list[FileHashRecord] = []

    for file_path in export_files:
        if file_path.exists() and file_path.is_file():
            sha, size = _compute_sha256(file_path)
            try:
                rel = str(file_path.relative_to(export_root))
            except ValueError:
                rel = file_path.name
            file_records.append(
                FileHashRecord(
                    file_name=file_path.name,
                    relative_path=rel,
                    sha256=sha,
                    size_bytes=size,
                )
            )

    return ExportManifest(
        manifest_version="1.0",
        project_name=project_name,
        fidelichem_version=version,
        timestamp_utc=datetime.now(UTC).isoformat(),
        exported_files=tuple(file_records),
        summary_counts=dict(summary_counts or {}),
        parameters=dict(parameters or {}),
    )


def write_export_manifest(
    manifest: ExportManifest,
    target_path: Path,
) -> Path:
    """Save an ExportManifest as formatted JSON."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return target_path


__all__ = ["create_export_manifest", "write_export_manifest"]
