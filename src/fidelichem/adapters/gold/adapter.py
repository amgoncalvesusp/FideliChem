"""First-class evidence adapter for CCDC GOLD docking campaigns."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fidelichem.adapters.base import (
    build_import_plan,
    compute_source_artifacts,
    scan_source_files,
)
from fidelichem.adapters.gold.parsers import (
    parse_gold_conf,
    parse_gold_mol2,
    parse_gold_ranking,
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


class GoldAdapter:
    """Evidence adapter parsing CCDC GOLD runs, rankings, and MOL2 solutions."""

    adapter_id = "fidelichem.gold"

    adapter_version = "0.1.0"
    display_name = "CCDC GOLD Docking Adapter"

    def probe(self, source: Path) -> DetectionReport:
        """Probe source for standard GOLD output files."""
        if not source.exists():
            return DetectionReport(
                confidence=0.0,
                detected_format="unknown",
                candidate_files=(),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        patterns = (
            "gold.conf",
            "gold.params",
            "gold.log",
            "bestranking.lst",
            "gold_ranking.txt",
            "ranking.csv",
            "gold_soln_*.mol2",
            "ranked_*.mol2",
            "*.mol2",
        )
        matches = scan_source_files(source, patterns=patterns)
        match_names = [f.as_posix() for f in matches]

        has_conf = any(
            "gold.conf" in f.lower() or "gold.params" in f.lower() for f in match_names
        )
        has_ranking = any(
            "bestranking.lst" in f.lower() or "gold_ranking" in f.lower()
            for f in match_names
        )
        has_solutions = any("gold_soln" in f.lower() for f in match_names)

        if has_conf or (has_ranking and has_solutions):
            return DetectionReport(
                confidence=0.95,
                detected_format="gold_docking_campaign",
                candidate_files=tuple(match_names),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )
        if has_solutions or has_ranking:
            return DetectionReport(
                confidence=0.85,
                detected_format="gold_solutions",
                candidate_files=tuple(match_names),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )
        if match_names:
            return DetectionReport(
                confidence=0.5,
                detected_format="possible_gold",
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
        """Generate content-addressed import plan for GOLD campaign."""
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
        """Parse all GOLD artifacts into targets, runs, compounds, poses, and scores."""
        source_root = Path(plan.source_root)
        source_artifacts: list[SourceArtifactRecord] = []
        qc_messages: list[QCIssue] = []

        file_hash_map = dict(plan.file_hashes)
        for rel_path in plan.source_files:
            file_path = source_root / rel_path
            sha = file_hash_map.get(rel_path, "")
            stat = file_path.stat() if file_path.exists() else None
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC) if stat else None
            size = stat.st_size if stat else 0
            if "gold.conf" in rel_path.lower():
                file_type = "gold_conf"
            elif rel_path.lower().endswith(".mol2"):
                file_type = "mol2"
            else:
                file_type = "txt"

            source_artifacts.append(
                SourceArtifactRecord(
                    relative_path=rel_path,
                    sha256=sha,
                    size_bytes=size,
                    file_type=file_type,
                    mtime=mtime,
                )
            )

        # 1. Parse gold.conf for target and run parameters
        conf_file_rel = next(
            (
                f
                for f in plan.source_files
                if f.lower().endswith("gold.conf") or f.lower().endswith("gold.params")
            ),
            None,
        )
        target_name = source_root.name or "gold_target"
        fitness_func = "CHEMPLP"
        conf_params: dict[str, Any] = {}

        if conf_file_rel:
            conf_data = parse_gold_conf(source_root / conf_file_rel)
            target_name = conf_data.get("target_name") or target_name
            fitness_func = conf_data.get("fitness_function") or "CHEMPLP"
            conf_params = conf_data.get("params", {})

        target_record = TargetRecord(name=target_name)
        run_name = conf_params.get("run_name") or f"GOLD_{target_name}"
        run_record = DockingRunRecord(
            run_name=run_name,
            target_name=target_name,
            engine="GOLD",
            engine_version="GOLD-v5",
            parameters={"fitness_function": fitness_func, **conf_params},
        )

        compounds_map: dict[str, RawCompoundRecord] = {}
        poses: list[PoseRecord] = []
        scores: list[ScoreObservationRecord] = []

        # 2. Check for ranking file
        ranking_file_rel = next(
            (
                f
                for f in plan.source_files
                if (
                    f.lower().endswith("bestranking.lst")
                    or "gold_ranking" in f.lower()
                    or f.lower().endswith("ranking.csv")
                )
            ),
            None,
        )

        seen_pose_ids: set[str] = set()

        if ranking_file_rel:
            ranking_path = source_root / ranking_file_rel
            ranking_rows = parse_gold_ranking(ranking_path)

            for row in ranking_rows:
                lig_name = row["ligand_name"]
                soln_file = row["solution_file"]
                rank_num = row["rank"]
                pose_id = (
                    Path(soln_file).stem if soln_file else f"{lig_name}_pose_{rank_num}"
                )

                if pose_id in seen_pose_ids:
                    qc_messages.append(
                        QCIssue(
                            code="QC_DUPLICATE_POSE_ID",
                            message=f"Duplicate pose ID '{pose_id}' in ranking file",
                            severity=QCSeverity.WARNING,
                            source_file=ranking_file_rel,
                            entity_reference=lig_name,
                        )
                    )
                seen_pose_ids.add(pose_id)

                if soln_file and not (source_root / soln_file).exists():
                    qc_messages.append(
                        QCIssue(
                            code="QC_MISSING_SOLUTION_FILE",
                            message=(
                                f"Ranked solution file '{soln_file}' does not exist"
                            ),
                            severity=QCSeverity.WARNING,
                            source_file=ranking_file_rel,
                            entity_reference=lig_name,
                        )
                    )

                if lig_name not in compounds_map:
                    compounds_map[lig_name] = RawCompoundRecord(
                        source_system="gold",
                        source_value=lig_name,
                        source_artifact_path=ranking_file_rel,
                    )

                poses.append(
                    PoseRecord(
                        run_name=run_name,
                        compound_source_system="gold",
                        compound_source_value=lig_name,
                        source_pose_id=pose_id,
                        rank=rank_num,
                        structure_artifact_path=soln_file or ranking_file_rel,
                    )
                )

                for score_key, val in row["scores"].items():
                    scores.append(
                        ScoreObservationRecord(
                            run_name=run_name,
                            compound_source_value=lig_name,
                            source_pose_id=pose_id,
                            score_key=score_key,
                            raw_value=val,
                            source_artifact_path=ranking_file_rel,
                        )
                    )

        # 3. Parse MOL2 solution files directly
        mol2_files = [f for f in plan.source_files if f.lower().endswith(".mol2")]
        for mol2_rel in mol2_files:
            mol2_path = source_root / mol2_rel
            mol2_poses = parse_gold_mol2(mol2_path)
            for idx, mp in enumerate(mol2_poses, start=1):
                lig_name = mp["ligand_name"]
                mol_smiles = mp.get("smiles")
                pose_id = (
                    f"{mol2_path.stem}_{idx}" if len(mol2_poses) > 1 else mol2_path.stem
                )

                if lig_name not in compounds_map:
                    compounds_map[lig_name] = RawCompoundRecord(
                        source_system="gold",
                        source_value=lig_name,
                        source_smiles=mol_smiles,
                        source_artifact_path=mol2_rel,
                    )
                elif compounds_map[lig_name].source_smiles is None and mol_smiles:
                    compounds_map[lig_name] = RawCompoundRecord(
                        source_system="gold",
                        source_value=lig_name,
                        source_smiles=mol_smiles,
                        source_artifact_path=compounds_map[
                            lig_name
                        ].source_artifact_path,
                    )

                if pose_id not in seen_pose_ids:
                    seen_pose_ids.add(pose_id)
                    poses.append(
                        PoseRecord(
                            run_name=run_name,
                            compound_source_system="gold",
                            compound_source_value=lig_name,
                            source_pose_id=pose_id,
                            rank=idx,
                            structure_artifact_path=mol2_rel,
                        )
                    )
                    for score_key, val in mp["scores"].items():
                        scores.append(
                            ScoreObservationRecord(
                                run_name=run_name,
                                compound_source_value=lig_name,
                                source_pose_id=pose_id,
                                score_key=score_key,
                                raw_value=val,
                                source_artifact_path=mol2_rel,
                            )
                        )

        return ImportBundle(
            plan=plan,
            targets=(target_record,),
            docking_runs=(run_record,),
            compounds=tuple(compounds_map.values()),
            poses=tuple(poses),
            scores=tuple(scores),
            source_artifacts=tuple(source_artifacts),
            qc_messages=tuple(qc_messages),
            provenance={"adapter": self.adapter_id, "version": self.adapter_version},
        )

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        """Validate parsed GOLD bundle."""
        errors: list[str] = []
        warnings: list[str] = []

        if not bundle.source_artifacts:
            errors.append("Bundle contains no source artifacts")

        if not bundle.compounds:
            errors.append("No compounds were parsed from GOLD campaign")

        if not bundle.poses:
            errors.append("No docking poses were extracted")

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


__all__ = ["GoldAdapter"]
