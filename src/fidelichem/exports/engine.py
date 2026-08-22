"""Unified Export Engine coordinating tabular exports, reports, and manifests."""

from __future__ import annotations

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
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_files: list[Path] = []

        # 1. Export in chosen formats
        for fmt in opts.formats:
            if fmt == ExportFormat.CSV:
                csv_file = output_dir / f"{project_name}_candidates.csv"
                export_to_csv(records, csv_file)
                generated_files.append(csv_file)
            elif fmt == ExportFormat.JSON:
                json_file = output_dir / f"{project_name}_candidates.json"
                export_to_json(records, json_file)
                generated_files.append(json_file)
            elif fmt == ExportFormat.XLSX:
                xlsx_file = output_dir / f"{project_name}_candidates.xlsx"
                export_to_xlsx(records, xlsx_file)
                generated_files.append(xlsx_file)
            elif fmt == ExportFormat.PARQUET:
                parquet_file = output_dir / f"{project_name}_candidates.parquet"
                export_to_parquet(records, parquet_file)
                generated_files.append(parquet_file)
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
            summary_counts={"total_records": len(records)},
            parameters=parameters,
        )
        manifest_path = output_dir / "manifest.json"
        write_export_manifest(manifest, manifest_path)
        generated_files.append(manifest_path)

        return ExportResult(
            manifest_path=str(manifest_path),
            files=[str(f) for f in generated_files],
            total_records=len(records),
            manifest=manifest,
        )


__all__ = ["ExportEngine"]
