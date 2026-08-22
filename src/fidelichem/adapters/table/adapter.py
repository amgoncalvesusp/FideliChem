"""Universal Table Adapter for generic CSV, TSV, JSON, JSONL, and tabular datasets."""

from __future__ import annotations

import contextlib
import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fidelichem.adapters.base import (
    build_import_plan,
    compute_source_artifacts,
    scan_source_files,
)
from fidelichem.adapters.table.readers import (
    detect_format,
    read_table_records,
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
from fidelichem.domain.table_importer import TableMappingSchema


def _safe_slug(value: str) -> str:
    """Normalize arbitrary string into a valid lowercase slug for source_system."""
    slug = re.sub(r"[^a-z0-9._-]", "_", value.strip().lower())
    slug = re.sub(r"^[._-]+", "", slug)
    return slug or "table_import"


class UniversalTableAdapter:
    """Configurable evidence adapter for arbitrary tabular molecular/docking files."""

    adapter_id = "fidelichem.universal_table"
    adapter_version = "0.1.0"
    display_name = "Universal Tabular Evidence Adapter"

    def probe(self, source: Path) -> DetectionReport:
        """Scan source for supported tabular data formats."""
        if not source.exists():
            return DetectionReport(
                confidence=0.0,
                detected_format="unknown",
                candidate_files=(),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        patterns = (
            "*.csv",
            "*.tsv",
            "*.parquet",
            "*.xlsx",
            "*.xls",
            "*.json",
            "*.jsonl",
            "*.ndjson",
        )
        matches = scan_source_files(source, patterns=patterns)
        table_files = [
            f.as_posix()
            for f in matches
            if detect_format(source / f if source.is_dir() else source) != "unknown"
        ]

        if table_files:
            return DetectionReport(
                confidence=0.8,
                detected_format="tabular",
                candidate_files=tuple(table_files),
                requires_user_mapping=True,
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
        """Compute artifacts and build immutable plan with mapping schema."""
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
        """Parse tabular files row by row into canonical domain models."""
        source_root = Path(plan.source_root)
        source_artifacts: list[SourceArtifactRecord] = []
        targets_map: dict[str, TargetRecord] = {}
        docking_runs_map: dict[str, DockingRunRecord] = {}
        compounds: list[RawCompoundRecord] = []
        poses: list[PoseRecord] = []
        scores: list[ScoreObservationRecord] = []
        qc_messages: list[QCIssue] = []

        # Parse mapping schema from plan options
        options_dict = dict(plan.options) if plan.options else {}
        schema_raw = options_dict.get("schema")
        schema = (
            TableMappingSchema.model_validate(schema_raw)
            if schema_raw is not None
            else TableMappingSchema()
        )

        file_hash_map = dict(plan.file_hashes)

        for rel_path in plan.source_files:
            file_path = source_root / rel_path
            sha = file_hash_map.get(rel_path, "")
            stat = file_path.stat() if file_path.exists() else None
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC) if stat else None
            size = stat.st_size if stat else 0
            fmt = detect_format(file_path)

            source_artifacts.append(
                SourceArtifactRecord(
                    relative_path=rel_path,
                    sha256=sha,
                    size_bytes=size,
                    file_type=fmt if fmt != "unknown" else "csv",
                    mtime=mtime,
                )
            )

            if not file_path.exists():
                qc_messages.append(
                    QCIssue(
                        code="QC_FILE_MISSING",
                        message=f"Planned table file '{rel_path}' not found",
                        severity=QCSeverity.ERROR,
                        source_file=rel_path,
                    )
                )
                continue

            ident = schema.identity

            for row_idx, record in enumerate(
                read_table_records(file_path, schema), start=1
            ):
                # 1. Target resolution
                target_name = (
                    str(record[ident.target_name_column])
                    if ident.target_name_column and record.get(ident.target_name_column)
                    else ident.target_name_default
                )
                if target_name and target_name not in targets_map:
                    targets_map[target_name] = TargetRecord(name=target_name)

                # 2. Docking run resolution
                run_name = (
                    str(record[ident.run_name_column])
                    if ident.run_name_column and record.get(ident.run_name_column)
                    else ident.run_name_default
                )
                if run_name and run_name not in docking_runs_map:
                    docking_runs_map[run_name] = DockingRunRecord(
                        run_name=run_name,
                        target_name=target_name,
                        engine="universal_table",
                    )

                # 3. Compound resolution
                source_sys_raw = (
                    str(record[ident.source_system_column])
                    if ident.source_system_column
                    and record.get(ident.source_system_column)
                    else ident.source_system_default
                )
                source_system = _safe_slug(source_sys_raw)

                source_val_raw = (
                    record.get(ident.molecule_id_column)
                    if ident.molecule_id_column
                    else None
                ) or (
                    record.get(ident.molecule_name_column)
                    if ident.molecule_name_column
                    else None
                )
                source_value = (
                    str(source_val_raw).strip()
                    if source_val_raw is not None and str(source_val_raw).strip()
                    else f"row_{row_idx}"
                )

                smiles = (
                    str(record[ident.smiles_column]).strip()
                    if ident.smiles_column and record.get(ident.smiles_column)
                    else None
                )
                inchikey = (
                    str(record[ident.inchikey_column]).strip()
                    if ident.inchikey_column and record.get(ident.inchikey_column)
                    else None
                )

                ph_raw = (
                    record.get(ident.preparation_ph_column)
                    if ident.preparation_ph_column
                    else ident.preparation_ph_default
                )
                ph: float | None = None
                if ph_raw is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        ph = float(ph_raw)

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

                # 4. Pose resolution
                pose_id = (
                    str(record[ident.pose_id_column]).strip()
                    if ident.pose_id_column and record.get(ident.pose_id_column)
                    else f"pose_{row_idx}"
                )
                rank = 1
                rank_raw = record.get(ident.rank_column) if ident.rank_column else None
                if rank_raw is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        rank = max(1, int(str(rank_raw)))

                poses.append(
                    PoseRecord(
                        run_name=run_name,
                        compound_source_system=source_system,
                        compound_source_value=source_value,
                        source_pose_id=pose_id,
                        rank=rank,
                        structure_artifact_path=rel_path,
                    )
                )

                # 5. Score observations (strictly preserves missing/None data)
                for score_mapping in schema.scores:
                    raw_val = record.get(score_mapping.column_name)
                    if raw_val is not None:
                        try:
                            score_val = float(raw_val)
                            if math.isfinite(score_val):
                                scores.append(
                                    ScoreObservationRecord(
                                        run_name=run_name,
                                        compound_source_value=source_value,
                                        source_pose_id=pose_id,
                                        score_key=score_mapping.score_key,
                                        raw_value=score_val,
                                        source_artifact_path=rel_path,
                                    )
                                )
                            else:
                                raise ValueError("Score is non-finite")
                        except (ValueError, TypeError):
                            qc_messages.append(
                                QCIssue(
                                    code="QC_INVALID_SCORE",
                                    message=(
                                        f"Invalid numeric score '{raw_val}' in "
                                        f"column '{score_mapping.column_name}' "
                                        f"at row {row_idx}"
                                    ),
                                    severity=QCSeverity.WARNING,
                                    source_file=rel_path,
                                    line_number=row_idx,
                                    entity_reference=source_value,
                                )
                            )

        return ImportBundle(
            plan=plan,
            targets=tuple(targets_map.values()),
            docking_runs=tuple(docking_runs_map.values()),
            compounds=tuple(compounds),
            poses=tuple(poses),
            scores=tuple(scores),
            source_artifacts=tuple(source_artifacts),
            qc_messages=tuple(qc_messages),
            provenance={"adapter": self.adapter_id, "version": self.adapter_version},
        )

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        """Validate parsed tabular bundle for semantic integrity."""
        errors: list[str] = []
        warnings: list[str] = []

        if not bundle.source_artifacts:
            errors.append("Bundle contains no source artifacts")

        if not bundle.compounds:
            errors.append("No compounds were parsed from tabular source")

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


__all__ = ["UniversalTableAdapter"]
