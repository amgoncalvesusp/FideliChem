"""Unified Export Engine coordinating tabular exports, reports, and manifests."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .manifest import create_export_manifest, write_export_manifest
from .models import ExportFormat, ExportOptions, ExportResult
from .reports import generate_methods_report
from .tabular import (
    export_to_csv,
    export_to_json,
    export_to_parquet,
    export_to_xlsx,
)


class ExportEngine:
    """Central engine generating export packages with cryptographic manifests."""

    def export_dataset(
        self,
        project_name: str,
        records: Sequence[Mapping[str, Any]],
        output_dir: Path,
        options: ExportOptions | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> ExportResult:
        """Export candidate dataset in requested formats and generate audit manifest."""
        opts = options or ExportOptions()
        selected_records = _select_records(records, opts)
        if not selected_records:
            raise ValueError("No records match the selected export contents")
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_files: list[Path] = []
        file_stem = _safe_project_stem(project_name)

        # 1. Export in chosen formats
        for fmt in opts.formats:
            if fmt == ExportFormat.CSV:
                csv_file = output_dir / f"{file_stem}_candidates.csv"
                export_to_csv(selected_records, csv_file)
                generated_files.append(csv_file)
            elif fmt == ExportFormat.JSON:
                json_file = output_dir / f"{file_stem}_candidates.json"
                export_to_json(selected_records, json_file)
                generated_files.append(json_file)
            elif fmt == ExportFormat.XLSX:
                xlsx_file = output_dir / f"{file_stem}_candidates.xlsx"
                generated_files.append(export_to_xlsx(selected_records, xlsx_file))
            elif fmt == ExportFormat.PARQUET:
                parquet_file = output_dir / f"{file_stem}_candidates.parquet"
                generated_files.append(
                    export_to_parquet(selected_records, parquet_file)
                )
            elif fmt == ExportFormat.METHODS_REPORT:
                report_file = output_dir / "METHODS_REPORT.md"
                generate_methods_report(
                    project_name=project_name,
                    parameters=parameters or {},
                    output_path=report_file,
                )
                generated_files.append(report_file)

        # 2. Generate Manifest
        manifest = create_export_manifest(
            project_name=project_name,
            export_files=generated_files,
            export_root=output_dir,
            summary_counts={"total_records": len(selected_records)},
            parameters={
                **(parameters or {}),
                "include_scores": opts.include_scores,
                "include_interactions": opts.include_interactions,
                "include_dynamics": opts.include_dynamics,
                "include_provenance": opts.include_provenance,
            },
        )
        manifest_path = output_dir / "manifest.json"
        write_export_manifest(manifest, manifest_path)
        generated_files.append(manifest_path)

        return ExportResult(
            manifest_path=str(manifest_path),
            files=[str(f) for f in generated_files],
            total_records=len(selected_records),
            manifest=manifest,
        )


def _select_records(
    records: Sequence[Mapping[str, Any]],
    options: ExportOptions,
) -> tuple[Mapping[str, Any], ...]:
    """Apply export content switches without mutating the caller snapshot."""

    selected: list[Mapping[str, Any]] = []
    for record in records:
        evidence_type = record.get("evidence_type")
        if evidence_type == "score" and not options.include_scores:
            continue
        if evidence_type == "interaction" and not options.include_interactions:
            continue
        if evidence_type in {"md_run", "md_metric"} and not options.include_dynamics:
            continue

        copy = dict(record)
        if not options.include_provenance:
            for field in (
                "import_batch_id",
                "source_artifact_path",
                "coordinate_hash",
                "configuration_hash",
            ):
                copy.pop(field, None)
        selected.append(copy)
    return tuple(selected)


def _safe_project_stem(project_name: str) -> str:
    """Convert a user-controlled project name into one safe filename stem."""

    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", project_name.strip())
    candidate = candidate.strip("._")
    return candidate[:120] or "fidelichem-project"


__all__ = ["ExportEngine"]
