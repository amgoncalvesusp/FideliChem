"""Evidence adapter for DockLens mechanistic molecular interactions."""

from __future__ import annotations

import contextlib
import csv
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fidelichem.adapters.base import (
    build_import_plan,
    compute_source_artifacts,
    scan_source_files,
)
from fidelichem.adapters.table.readers import detect_delimiter
from fidelichem.domain.adapters import (
    DetectionReport,
    ImportBundle,
    ImportPlan,
    InteractionRecord,
    QCIssue,
    SourceArtifactRecord,
    ValidationReport,
)


class DockLensAdapter:
    """Evidence adapter parsing DockLens interactions and contact profiles."""

    adapter_id = "fidelichem.docklens"
    adapter_version = "0.1.0"
    display_name = "DockLens Mechanistic Interaction Profiler Adapter"

    def probe(self, source: Path) -> DetectionReport:
        """Probe source directory for DockLens interactions and profiles."""
        if not source.exists():
            return DetectionReport(
                confidence=0.0,
                detected_format="unknown",
                candidate_files=(),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        patterns = (
            "*docklens*.json",
            "*interaction*.json",
            "*contact*.json",
            "*docklens*.csv",
            "*interaction*.csv",
            "*plip*.json",
            "*plip*.csv",
            "*.docklens",
        )
        matches = scan_source_files(source, patterns=patterns)
        match_names = [f.as_posix() for f in matches]

        json_matches = [
            f
            for f in match_names
            if f.endswith(".json")
            and any(k in f.lower() for k in ("docklens", "interaction", "contact"))
        ]
        if json_matches:
            return DetectionReport(
                confidence=0.95,
                detected_format="docklens_json",
                candidate_files=tuple(match_names),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        csv_matches = [
            f
            for f in match_names
            if f.endswith((".csv", ".tsv"))
            and any(k in f.lower() for k in ("docklens", "interaction", "contact"))
        ]
        if csv_matches:
            return DetectionReport(
                confidence=0.9,
                detected_format="docklens_csv",
                candidate_files=tuple(match_names),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        if match_names:
            return DetectionReport(
                confidence=0.5,
                detected_format="possible_docklens",
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
        """Build content-addressed import plan for DockLens interaction evidence."""
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
        """Parse mechanistic interactions and contact profiles."""
        source_root = Path(plan.source_root)
        source_artifacts: list[SourceArtifactRecord] = []
        qc_messages: list[QCIssue] = []
        interactions: list[InteractionRecord] = []

        file_hash_map = dict(plan.file_hashes)
        for rel_path in plan.source_files:
            file_path = source_root / rel_path
            sha = file_hash_map.get(rel_path, "")
            stat = file_path.stat() if file_path.exists() else None
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC) if stat else None
            size = stat.st_size if stat else 0
            file_type = "json" if rel_path.endswith(".json") else "csv"

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
            lower_path = rel_path.lower()

            if lower_path.endswith(".json"):
                interactions.extend(self._parse_json(file_path, rel_path, qc_messages))
            elif lower_path.endswith((".csv", ".tsv")):
                interactions.extend(self._parse_csv(file_path, rel_path, qc_messages))

        return ImportBundle(
            plan=plan,
            targets=(),
            docking_runs=(),
            compounds=(),
            poses=(),
            scores=(),
            interactions=tuple(interactions),
            source_artifacts=tuple(source_artifacts),
            qc_messages=tuple(qc_messages),
            provenance={"adapter": self.adapter_id, "version": self.adapter_version},
        )

    def _parse_json(
        self,
        file_path: Path,
        rel_path: str,
        qc_messages: list[QCIssue],
    ) -> list[InteractionRecord]:
        records: list[InteractionRecord] = []
        with contextlib.suppress(Exception):
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)

            global_run = data.get("run_name") or data.get("run_id") or "docking_run"
            global_target = data.get("target_name") or data.get("target")

            items = (
                data.get("interactions")
                or data.get("contacts")
                or data.get("results")
                or []
            )
            if isinstance(data, list):
                items = data

            for item in items:
                if not isinstance(item, dict):
                    continue
                run_name = str(item.get("run_name") or global_run)
                cmpd_id = str(
                    item.get("compound_id")
                    or item.get("compound_source_value")
                    or item.get("ligand_id")
                    or item.get("ligand")
                    or "UNKNOWN_LIGAND"
                )
                pose_id = str(
                    item.get("pose_id")
                    or item.get("source_pose_id")
                    or item.get("pose")
                    or "P001"
                )
                residue = str(
                    item.get("residue")
                    or item.get("residue_name")
                    or item.get("target_residue")
                    or "UNK"
                )
                int_type = str(
                    item.get("interaction_type") or item.get("type") or "contact"
                )
                raw_target = item.get("target") or global_target
                target = str(raw_target) if raw_target else None

                dist = item.get("distance")
                dist_val = float(dist) if dist is not None else None
                ang = item.get("angle")
                ang_val = float(ang) if ang is not None else None
                freq = item.get("frequency") or item.get("occupancy")
                freq_val = float(freq) if freq is not None else None
                feat = item.get("ligand_feature") or item.get("feature")

                meta = {
                    "source_adapter": self.adapter_id,
                    **{
                        k: v
                        for k, v in item.items()
                        if k
                        not in (
                            "run_name",
                            "compound_id",
                            "pose_id",
                            "residue",
                            "interaction_type",
                            "type",
                            "distance",
                            "angle",
                            "occupancy",
                            "frequency",
                            "ligand_feature",
                        )
                    },
                }

                records.append(
                    InteractionRecord(
                        run_name=run_name,
                        compound_source_value=cmpd_id,
                        source_pose_id=pose_id,
                        target_name=target,
                        residue_name=residue,
                        interaction_type=int_type,
                        distance=dist_val,
                        angle=ang_val,
                        frequency=freq_val,
                        ligand_feature=str(feat) if feat else None,
                        metadata=meta,
                    )
                )
        return records

    def _parse_csv(
        self,
        file_path: Path,
        rel_path: str,
        qc_messages: list[QCIssue],
    ) -> list[InteractionRecord]:
        records: list[InteractionRecord] = []
        with contextlib.suppress(Exception):
            delim = detect_delimiter(file_path)
            with file_path.open(
                mode="r", encoding="utf-8", errors="replace", newline=""
            ) as f:
                reader = csv.DictReader(f, delimiter=delim)
                for row in reader:
                    run_name = str(
                        row.get("run_name") or row.get("run_id") or "docking_run"
                    )
                    cmpd_id = str(
                        row.get("compound_id")
                        or row.get("compound_source_value")
                        or row.get("ligand_id")
                        or row.get("ligand")
                        or "UNKNOWN_LIGAND"
                    )
                    pose_id = str(
                        row.get("pose_id")
                        or row.get("source_pose_id")
                        or row.get("pose")
                        or "P001"
                    )
                    residue = str(
                        row.get("residue")
                        or row.get("residue_name")
                        or row.get("target_residue")
                        or "UNK"
                    )
                    int_type = str(
                        row.get("interaction_type") or row.get("type") or "contact"
                    )
                    target = row.get("target") or row.get("target_name")

                    dist = row.get("distance")
                    dist_val = float(dist) if dist and dist.strip() else None
                    ang = row.get("angle")
                    ang_val = float(ang) if ang and ang.strip() else None
                    freq = row.get("frequency") or row.get("occupancy")
                    freq_val = float(freq) if freq and freq.strip() else None
                    feat = row.get("ligand_feature") or row.get("feature")

                    meta = {
                        "source_adapter": self.adapter_id,
                        **{
                            k: v
                            for k, v in row.items()
                            if k
                            not in (
                                "run_name",
                                "compound_id",
                                "pose_id",
                                "residue",
                                "interaction_type",
                                "type",
                                "distance",
                                "angle",
                                "occupancy",
                                "frequency",
                                "ligand_feature",
                            )
                        },
                    }

                    records.append(
                        InteractionRecord(
                            run_name=run_name,
                            compound_source_value=cmpd_id,
                            source_pose_id=pose_id,
                            target_name=str(target) if target else None,
                            residue_name=residue,
                            interaction_type=int_type,
                            distance=dist_val,
                            angle=ang_val,
                            frequency=freq_val,
                            ligand_feature=str(feat) if feat else None,
                            metadata=meta,
                        )
                    )
        return records

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        """Validate parsed DockLens bundle."""
        errors: list[str] = []
        warnings: list[str] = []

        if not bundle.source_artifacts:
            errors.append("Bundle contains no source artifacts")

        if not bundle.interactions:
            errors.append("No interactions were parsed from DockLens evidence")

        return ValidationReport(
            is_valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
            qc_issues=bundle.qc_messages,
        )


__all__ = ["DockLensAdapter"]
