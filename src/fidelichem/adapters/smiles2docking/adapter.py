"""Evidence adapter for SMILES2Docking ligand 3D preparation and protonation."""

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
    QCIssue,
    RawCompoundRecord,
    SourceArtifactRecord,
    ValidationReport,
)


class Smiles2DockingAdapter:
    """Evidence adapter parsing SMILES2Docking runs and protonation states."""

    adapter_id = "fidelichem.smiles2docking"
    adapter_version = "0.1.0"
    display_name = "SMILES2Docking Ligand Preparation Adapter"

    def probe(self, source: Path) -> DetectionReport:
        """Probe source directory for SMILES2Docking run descriptors."""
        if not source.exists():
            return DetectionReport(
                confidence=0.0,
                detected_format="unknown",
                candidate_files=(),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        patterns = (
            "*smiles2docking*.json",
            "run.json",
            "manifest.json",
            "prepared_*.sdf",
            "prepared_*.mol2",
            "*.sdf",
        )
        matches = scan_source_files(source, patterns=patterns)
        match_names = [f.as_posix() for f in matches]

        json_descriptors = [
            f
            for f in match_names
            if f.endswith(".json")
            and (
                "smiles2docking" in f.lower()
                or f.lower() in ("run.json", "manifest.json")
            )
        ]

        if json_descriptors:
            return DetectionReport(
                confidence=0.95,
                detected_format="smiles2docking_run",
                candidate_files=tuple(match_names),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        sdf_or_mol2 = [
            f
            for f in match_names
            if "prepared" in f.lower() or f.endswith((".sdf", ".mol2"))
        ]
        if sdf_or_mol2:
            return DetectionReport(
                confidence=0.75,
                detected_format="smiles2docking_structures",
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
        """Build content-addressed import plan for SMILES2Docking evidence."""
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
        """Parse prepared compounds, pH, tautomer states, and structure paths."""
        verify_import_plan(plan)
        source_root = Path(plan.source_root)
        source_artifacts: list[SourceArtifactRecord] = []
        qc_messages: list[QCIssue] = []
        compounds: list[RawCompoundRecord] = []

        file_hash_map = dict(plan.file_hashes)
        for rel_path in plan.source_files:
            file_path = source_root / rel_path
            sha = file_hash_map.get(rel_path, "")
            stat = file_path.stat() if file_path.exists() else None
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC) if stat else None
            size = stat.st_size if stat else 0
            file_type = (
                "json"
                if rel_path.endswith(".json")
                else ("sdf" if rel_path.endswith(".sdf") else "mol2")
            )

            source_artifacts.append(
                SourceArtifactRecord(
                    relative_path=rel_path,
                    sha256=sha,
                    size_bytes=size,
                    file_type=file_type,
                    mtime=mtime,
                )
            )

        json_files = [
            f
            for f in plan.source_files
            if f.endswith(".json")
            and (
                "smiles2docking" in f.lower()
                or f.lower() in ("run.json", "manifest.json")
            )
        ]

        seen_cmpd_ids: set[str] = set()

        for json_rel in json_files:
            json_path = source_root / json_rel
            with contextlib.suppress(Exception):
                content = json_path.read_text(encoding="utf-8")
                data = json.loads(content)
                global_ph = (
                    data.get("target_ph")
                    or data.get("preparation_ph")
                    or data.get("ph")
                )
                global_ph_val = float(global_ph) if global_ph is not None else None
                prot_engine = data.get("protonation_engine") or data.get(
                    "protonation_backend"
                )
                opt_method = data.get("optimization_method") or data.get(
                    "energy_minimization"
                )

                items = (
                    data.get("compounds")
                    or data.get("ligands")
                    or data.get("results")
                    or []
                )
                if isinstance(data, list):
                    items = data

                for idx, item in enumerate(items, start=1):
                    if not isinstance(item, dict):
                        continue
                    cmpd_id = str(
                        item.get("compound_id")
                        or item.get("id")
                        or item.get("name")
                        or f"LIG_{idx}"
                    )
                    state_smiles = (
                        item.get("state_smiles")
                        or item.get("protonated_smiles")
                        or item.get("smiles")
                    )
                    initial_smiles = item.get("initial_smiles")
                    struct_file = (
                        item.get("structure_file")
                        or item.get("structure_path")
                        or item.get("file")
                    )

                    item_ph = item.get("ph")
                    eff_ph = float(item_ph) if item_ph is not None else global_ph_val

                    meta = {
                        "source_adapter": self.adapter_id,
                        "initial_smiles": initial_smiles,
                        "protonation_engine": (
                            prot_engine or item.get("protonation_engine")
                        ),
                        "optimization_method": (
                            opt_method or item.get("optimization_method")
                        ),
                        "structure_file": struct_file,
                        **{
                            k: v
                            for k, v in item.items()
                            if k
                            not in (
                                "compound_id",
                                "id",
                                "smiles",
                                "state_smiles",
                                "protonated_smiles",
                            )
                        },
                    }

                    eff_smiles = (
                        str(state_smiles)
                        if state_smiles
                        else (str(initial_smiles) if initial_smiles else None)
                    )

                    seen_cmpd_ids.add(cmpd_id)
                    compounds.append(
                        RawCompoundRecord(
                            source_system="smiles2docking",
                            source_value=cmpd_id,
                            source_smiles=eff_smiles,
                            preparation_ph=eff_ph,
                            source_artifact_path=struct_file or json_rel,
                            metadata=meta,
                        )
                    )

        return ImportBundle(
            plan=plan,
            targets=(),
            docking_runs=(),
            compounds=tuple(compounds),
            poses=(),
            scores=(),
            source_artifacts=tuple(source_artifacts),
            qc_messages=tuple(qc_messages),
            provenance={"adapter": self.adapter_id, "version": self.adapter_version},
        )

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        """Validate parsed SMILES2Docking bundle."""
        errors: list[str] = []
        warnings: list[str] = []

        if not bundle.source_artifacts:
            errors.append("Bundle contains no source artifacts")

        if not bundle.compounds:
            errors.append(
                "No prepared ligands were parsed from SMILES2Docking evidence"
            )

        return ValidationReport(
            is_valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
            qc_issues=bundle.qc_messages,
        )


__all__ = ["Smiles2DockingAdapter"]
