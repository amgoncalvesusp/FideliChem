"""Reference FakeAdapter implementation for validation and testing."""

from __future__ import annotations

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
    DockingRunRecord,
    ImportBundle,
    ImportPlan,
    PoseRecord,
    QCIssue,
    QCSeverity,
    RawCompoundRecord,
    ScoreObservationRecord,
    SourceArtifactRecord,
    TargetRecord,
    ValidationReport,
)


class FakeAdapter:
    """Reference adapter parsing .fake.json manifests and mock docking runs."""

    adapter_id = "fidelichem.fake"
    adapter_version = "0.1.0"
    display_name = "FideliChem Reference Fake Adapter"

    def probe(self, source: Path) -> DetectionReport:
        """Scan source directory or file for fake docking artifacts."""
        if not source.exists():
            return DetectionReport(
                confidence=0.0,
                detected_format="unknown",
                candidate_files=(),
                suggested_adapter=self.adapter_id,
            )

        matches = scan_source_files(
            source,
            patterns=("*.fake.json", "*.fake", "*.json"),
        )
        fake_files = [
            f.as_posix()
            for f in matches
            if f.name.endswith(".fake.json")
            or f.name.endswith(".fake")
            or "fake" in f.name.lower()
        ]

        if fake_files:
            return DetectionReport(
                confidence=1.0,
                detected_format="fake_docking_v1",
                candidate_files=tuple(fake_files),
                suggested_adapter=self.adapter_id,
            )

        return DetectionReport(
            confidence=0.0,
            detected_format="unknown",
            candidate_files=(),
            suggested_adapter=self.adapter_id,
        )

    def plan(
        self,
        source: Path,
        options: Mapping[str, Any] | None = None,
    ) -> ImportPlan:
        """Compute artifacts and build immutable plan."""
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
        """Read source files and build canonical bundle."""
        verify_import_plan(plan)
        source_root = Path(plan.source_root)
        source_artifacts: list[SourceArtifactRecord] = []
        targets: list[TargetRecord] = []
        docking_runs: list[DockingRunRecord] = []
        compounds: list[RawCompoundRecord] = []
        poses: list[PoseRecord] = []
        scores: list[ScoreObservationRecord] = []
        qc_messages: list[QCIssue] = []

        file_hash_map = dict(plan.file_hashes)

        for rel_path in plan.source_files:
            file_path = source_root / rel_path
            sha = file_hash_map.get(rel_path, "")
            stat = file_path.stat() if file_path.exists() else None
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC) if stat else None
            size = stat.st_size if stat else 0

            source_artifacts.append(
                SourceArtifactRecord(
                    relative_path=rel_path,
                    sha256=sha,
                    size_bytes=size,
                    file_type="json",
                    mtime=mtime,
                )
            )

            if not file_path.exists():
                qc_messages.append(
                    QCIssue(
                        code="QC_FILE_MISSING",
                        message=f"Planned file '{rel_path}' does not exist",
                        severity=QCSeverity.ERROR,
                        source_file=rel_path,
                    )
                )
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                data = json.loads(content)
            except Exception as err:
                qc_messages.append(
                    QCIssue(
                        code="QC_CORRUPT_JSON",
                        message=f"Could not parse JSON in '{rel_path}': {err}",
                        severity=QCSeverity.ERROR,
                        source_file=rel_path,
                    )
                )
                continue

            # Parse target if present
            if "target" in data and isinstance(data["target"], dict):
                t = data["target"]
                targets.append(
                    TargetRecord(
                        name=t.get("name", "UnknownTarget"),
                        accession=t.get("accession"),
                        pdb_id=t.get("pdb_id"),
                        chain=t.get("chain"),
                    )
                )

            # Parse docking run if present
            run_name = "DefaultRun"
            if "docking_run" in data and isinstance(data["docking_run"], dict):
                r = data["docking_run"]
                run_name = r.get("run_name", "DefaultRun")
                docking_runs.append(
                    DockingRunRecord(
                        run_name=run_name,
                        engine=r.get("engine", "FakeEngine"),
                        engine_version=r.get("engine_version"),
                    )
                )

            # Parse compounds, poses, and scores
            raw_compounds = data.get("compounds", [])
            for item in raw_compounds:
                if not isinstance(item, dict):
                    continue

                source_system = str(item.get("source_system", "fake")).lower()
                source_value = str(item.get("source_value", ""))
                smiles = item.get("smiles")
                inchikey = item.get("inchikey")
                ph = item.get("preparation_ph")

                compounds.append(
                    RawCompoundRecord(
                        source_system=source_system,
                        source_value=source_value,
                        source_smiles=smiles,
                        source_inchikey=inchikey,
                        preparation_ph=ph,
                        source_artifact_path=rel_path,
                    )
                )

                pose_id = item.get("pose_id")
                rank = item.get("rank", 1)
                if pose_id:
                    poses.append(
                        PoseRecord(
                            run_name=run_name,
                            compound_source_system=source_system,
                            compound_source_value=source_value,
                            source_pose_id=str(pose_id),
                            rank=max(1, int(rank)),
                            structure_artifact_path=rel_path,
                        )
                    )

                # Score observation (strictly preserves missing data/None)
                raw_score = item.get("score")
                if raw_score is not None:
                    try:
                        score_val = float(raw_score)
                        scores.append(
                            ScoreObservationRecord(
                                run_name=run_name,
                                compound_source_value=source_value,
                                source_pose_id=str(pose_id) if pose_id else "pose_1",
                                score_key="fake.docking_score",
                                raw_value=score_val,
                                source_artifact_path=rel_path,
                            )
                        )

                    except (ValueError, TypeError):
                        qc_messages.append(
                            QCIssue(
                                code="QC_INVALID_SCORE",
                                message=(
                                    f"Invalid score value '{raw_score}' "
                                    f"for '{source_value}'"
                                ),
                                severity=QCSeverity.WARNING,
                                source_file=rel_path,
                                entity_reference=source_value,
                            )
                        )

        return ImportBundle(
            plan=plan,
            targets=tuple(targets),
            docking_runs=tuple(docking_runs),
            compounds=tuple(compounds),
            poses=tuple(poses),
            scores=tuple(scores),
            source_artifacts=tuple(source_artifacts),
            qc_messages=tuple(qc_messages),
            provenance={"adapter": self.adapter_id, "version": self.adapter_version},
        )

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        """Validate imported bundle against integrity constraints."""
        errors: list[str] = []
        warnings: list[str] = []

        if not bundle.source_artifacts:
            errors.append("Bundle contains no source artifacts")

        for qc in bundle.qc_messages:
            if qc.severity == QCSeverity.ERROR:
                errors.append(f"[{qc.code}] {qc.message}")
            elif qc.severity == QCSeverity.WARNING:
                warnings.append(f"[{qc.code}] {qc.message}")

        return ValidationReport(
            is_valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
            qc_issues=bundle.qc_messages,
        )


__all__ = ["FakeAdapter"]
