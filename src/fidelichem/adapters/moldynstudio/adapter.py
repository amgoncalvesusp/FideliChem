"""Evidence adapter for MolDynStudio simulation reports and metrics."""

from __future__ import annotations

import contextlib
import json
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


class MolDynStudioAdapter:
    """Evidence adapter parsing MolDynStudio simulation manifests and metrics."""

    adapter_id = "fidelichem.moldynstudio"
    adapter_version = "0.1.0"
    display_name = "MolDynStudio Molecular Dynamics Adapter"

    def probe(self, source: Path) -> DetectionReport:
        """Probe source directory for MolDynStudio results."""
        if not source.exists():
            return DetectionReport(
                confidence=0.0,
                detected_format="unknown",
                candidate_files=(),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        patterns = (
            "*fidelichem-md-result*.json",
            "*moldynstudio*.json",
            "*simulation*.json",
            "*moldyn*.csv",
            "*md_report*.json",
        )
        matches = scan_source_files(source, patterns=patterns)
        match_names = [f.as_posix() for f in matches]

        json_matches = [
            f
            for f in match_names
            if f.endswith(".json")
            and any(
                k in f.lower()
                for k in (
                    "fidelichem-md",
                    "moldynstudio",
                    "simulation",
                    "md_report",
                )
            )
        ]
        if json_matches:
            return DetectionReport(
                confidence=0.95,
                detected_format="moldynstudio_json",
                candidate_files=tuple(match_names),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        if match_names:
            return DetectionReport(
                confidence=0.5,
                detected_format="possible_moldynstudio",
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
        """Build content-addressed import plan for MolDynStudio evidence."""
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
        """Parse simulation parameters and analytical metrics."""
        verify_import_plan(plan)
        source_root = Path(plan.source_root)
        source_artifacts: list[SourceArtifactRecord] = []
        qc_messages: list[QCIssue] = []
        md_runs: list[MDRunRecord] = []
        md_metrics: list[MDMetricRecord] = []

        file_hash_map = dict(plan.file_hashes)
        for rel_path in plan.source_files:
            file_path = source_root / rel_path
            sha = file_hash_map.get(rel_path, "")
            stat = file_path.stat() if file_path.exists() else None
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC) if stat else None
            size = stat.st_size if stat else 0
            file_type = "json" if rel_path.endswith(".json") else "data"

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
            if rel_path.lower().endswith(".json"):
                with contextlib.suppress(Exception):
                    content = file_path.read_text(encoding="utf-8")
                    data = json.loads(content)

                    run_name = str(
                        data.get("run_name")
                        or data.get("run_id")
                        or data.get("simulation_id")
                        or f"md_run_{file_path.stem}"
                    )
                    tgt = data.get("target_name") or data.get("target")
                    cmpd = (
                        data.get("compound_id")
                        or data.get("compound")
                        or data.get("ligand_id")
                    )
                    pose = data.get("pose_id") or data.get("pose")

                    dur = data.get("duration_ns") or data.get("duration")
                    dur_val = float(dur) if dur is not None else None
                    temp = data.get("temperature_k") or data.get("temperature")
                    temp_val = float(temp) if temp is not None else None
                    dt = data.get("timestep_fs") or data.get("timestep")
                    dt_val = float(dt) if dt is not None else None
                    engine = str(data.get("engine") or "MolDynStudio/GROMACS")

                    md_runs.append(
                        MDRunRecord(
                            run_name=run_name,
                            target_name=str(tgt) if tgt else None,
                            compound_source_value=str(cmpd) if cmpd else None,
                            source_pose_id=str(pose) if pose else None,
                            duration_ns=dur_val,
                            temperature_k=temp_val,
                            timestep_fs=dt_val,
                            engine=engine,
                            parameters={
                                k: v
                                for k, v in data.items()
                                if k
                                not in (
                                    "run_name",
                                    "metrics",
                                    "results",
                                    "duration_ns",
                                    "temperature_k",
                                    "timestep_fs",
                                )
                            },
                        )
                    )

                    metrics_list = (
                        data.get("metrics")
                        or data.get("results")
                        or data.get("analytical_metrics")
                        or []
                    )
                    for m in metrics_list:
                        if not isinstance(m, dict):
                            continue
                        k = str(m.get("metric_key") or m.get("name") or "metric")
                        unit = m.get("unit")
                        mean_val = (
                            float(m["mean"])
                            if "mean" in m and m["mean"] is not None
                            else None
                        )
                        std_val = (
                            float(m["std"])
                            if "std" in m and m["std"] is not None
                            else None
                        )
                        min_val = (
                            float(m["min"])
                            if "min" in m and m["min"] is not None
                            else None
                        )
                        max_val = (
                            float(m["max"])
                            if "max" in m and m["max"] is not None
                            else None
                        )

                        t_pts = tuple(float(x) for x in m.get("time_points", []))
                        vals = tuple(float(x) for x in m.get("values", []))

                        md_metrics.append(
                            MDMetricRecord(
                                run_name=run_name,
                                metric_key=k,
                                unit=str(unit) if unit else None,
                                mean_value=mean_val,
                                std_value=std_val,
                                min_value=min_val,
                                max_value=max_val,
                                compound_source_value=(str(cmpd) if cmpd else None),
                                source_pose_id=str(pose) if pose else None,
                                source_artifact_path=rel_path,
                                time_points=t_pts,
                                values=vals,
                                metadata=m,
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
        """Validate parsed MolDynStudio bundle."""
        errors: list[str] = []
        warnings: list[str] = []

        if not bundle.source_artifacts:
            errors.append("Bundle contains no source artifacts")

        if not bundle.md_runs and not bundle.md_metrics:
            errors.append(
                "No simulation runs or MD metrics were parsed "
                "from MolDynStudio evidence"
            )

        return ValidationReport(
            is_valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
            qc_issues=bundle.qc_messages,
        )


__all__ = ["MolDynStudioAdapter"]
