"""Evidence adapter for GROMACS analytical output files (XVG, metrics)."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fidelichem.adapters.base import (
    build_import_plan,
    compute_source_artifacts,
    scan_source_files,
    verify_import_plan,
)
from fidelichem.domain.adapters import (
    DetectionReport,
    ImportBundle,
    ImportPlan,
    MDMetricRecord,
    MDRunRecord,
    QCIssue,
    SourceArtifactRecord,
    ValidationReport,
)

from .xvg import parse_xvg


class GromacsAdapter:
    """Evidence adapter parsing GROMACS analytical curves and MD run metrics."""

    adapter_id = "fidelichem.gromacs"
    adapter_version = "0.1.0"
    display_name = "GROMACS Molecular Dynamics Analytical Adapter"

    def probe(self, source: Path) -> DetectionReport:
        """Probe source directory for GROMACS XVG analytical outputs."""
        if not source.exists():
            return DetectionReport(
                confidence=0.0,
                detected_format="unknown",
                candidate_files=(),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        patterns = (
            "*.xvg",
            "*rmsd*.xvg",
            "*rmsf*.xvg",
            "*rgyr*.xvg",
            "*sasa*.xvg",
            "*energy*.xvg",
            "*gromacs*.json",
            "*gromacs*.csv",
        )
        matches = scan_source_files(source, patterns=patterns)
        match_names = [f.as_posix() for f in matches]

        xvg_matches = [f for f in match_names if f.endswith(".xvg")]
        if xvg_matches:
            return DetectionReport(
                confidence=0.95,
                detected_format="gromacs_xvg",
                candidate_files=tuple(match_names),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        if match_names:
            return DetectionReport(
                confidence=0.5,
                detected_format="possible_gromacs",
                candidate_files=tuple(match_names),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        return DetectionReport(
            confidence=0.0,
            detected_format="unknown",
            candidate_files=(),
            requires_user_mapping=False,
            suggested_adapter=self.adapter_id,
        )

    def plan(
        self,
        source: Path,
        options: Mapping[str, Any] | None = None,
    ) -> ImportPlan:
        """Build content-addressed import plan for GROMACS analytical evidence."""
        detection = self.probe(source)
        candidate_files = (
            list(detection.candidate_files)
            if detection.candidate_files
            else [p.as_posix() for p in scan_source_files(source)]
        )
        artifacts = compute_source_artifacts(source, candidate_files)
        return build_import_plan(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            source_root=str(source),
            artifacts=artifacts,
            options=options,
        )

    def parse(self, plan: ImportPlan) -> ImportBundle:
        """Parse XVG curves and MD metrics from GROMACS analytical files."""
        verify_import_plan(plan)
        source_root = Path(plan.source_root)
        source_artifacts: list[SourceArtifactRecord] = []
        qc_messages: list[QCIssue] = []
        md_metrics: list[MDMetricRecord] = []
        md_runs: list[MDRunRecord] = []

        run_name = "gromacs_md_run"

        file_hash_map = dict(plan.file_hashes)
        for rel_path in plan.source_files:
            file_path = source_root / rel_path
            sha = file_hash_map.get(rel_path, "")
            stat = file_path.stat() if file_path.exists() else None
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC) if stat else None
            size = stat.st_size if stat else 0
            file_type = "xvg" if rel_path.endswith(".xvg") else "data"

            source_artifacts.append(
                SourceArtifactRecord(
                    relative_path=rel_path,
                    sha256=sha,
                    size_bytes=size,
                    file_type=file_type,
                    mtime=mtime,
                )
            )

        for rel_path in plan.source_files:
            file_path = source_root / rel_path
            if rel_path.lower().endswith(".xvg"):
                with contextlib.suppress(Exception):
                    xvg = parse_xvg(file_path)
                    base_name = file_path.stem.lower()
                    metric_key = (
                        base_name
                        if base_name
                        else (
                            xvg.title.lower().replace(" ", "_")
                            if xvg.title
                            else "md_metric"
                        )
                    )

                    for _s_idx, (legend, values, summary) in enumerate(
                        zip(
                            xvg.series_legends,
                            xvg.series_values,
                            xvg.series_summaries,
                            strict=False,
                        )
                    ):
                        full_metric_key = (
                            metric_key
                            if len(xvg.series_legends) == 1
                            else f"{metric_key}_{legend.lower().replace(' ', '_')}"
                        )
                        md_metrics.append(
                            MDMetricRecord(
                                run_name=run_name,
                                metric_key=full_metric_key,
                                unit=xvg.yaxis_label or None,
                                mean_value=summary.get("mean"),
                                std_value=summary.get("std"),
                                min_value=summary.get("min"),
                                max_value=summary.get("max"),
                                source_artifact_path=rel_path,
                                time_points=xvg.time_points,
                                values=values,
                                metadata={
                                    "title": xvg.title,
                                    "legend": legend,
                                    "xaxis": xvg.xaxis_label,
                                    "yaxis": xvg.yaxis_label,
                                },
                            )
                        )

        if md_metrics:
            md_runs.append(
                MDRunRecord(
                    run_name=run_name,
                    engine="GROMACS",
                    parameters={"source_files": list(plan.source_files)},
                )
            )

        return ImportBundle(
            plan=plan,
            targets=(),
            docking_runs=(),
            compounds=(),
            poses=(),
            scores=(),
            interactions=(),
            md_runs=tuple(md_runs),
            md_metrics=tuple(md_metrics),
            source_artifacts=tuple(source_artifacts),
            qc_messages=tuple(qc_messages),
            provenance={"adapter": self.adapter_id, "version": self.adapter_version},
        )

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        """Validate parsed GROMACS bundle."""
        errors: list[str] = []
        warnings: list[str] = []

        if not bundle.source_artifacts:
            errors.append("Bundle contains no source artifacts")

        if not bundle.md_metrics:
            errors.append("No MD metrics were parsed from GROMACS evidence")

        return ValidationReport(
            is_valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
            qc_issues=bundle.qc_messages,
        )


__all__ = ["GromacsAdapter"]
