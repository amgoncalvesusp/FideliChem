"""Evidence adapter for SMILES2Select filtering, QED, and selection decisions."""

from __future__ import annotations

import csv
import json
import sqlite3
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
from fidelichem.adapters.table.readers import detect_delimiter
from fidelichem.domain.adapters import (
    DetectionReport,
    ImportBundle,
    ImportPlan,
    QCIssue,
    RawCompoundRecord,
    SourceArtifactRecord,
    ValidationReport,
)


class Smiles2SelectAdapter:
    """Evidence adapter parsing SMILES2Select runs from SQLite, JSON, or CSV files."""

    adapter_id = "fidelichem.smiles2select"
    adapter_version = "0.1.0"
    display_name = "SMILES2Select Selection Adapter"

    def probe(self, source: Path) -> DetectionReport:
        """Probe source for SMILES2Select databases or export files."""
        if not source.exists():
            return DetectionReport(
                confidence=0.0,
                detected_format="unknown",
                candidate_files=(),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        patterns = (
            "*.sqlite",
            "*.db",
            "*smiles2select*.json",
            "*selection*.json",
            "*smiles2select*.csv",
            "*selection*.csv",
        )
        matches = scan_source_files(source, patterns=patterns)
        match_names = [f.as_posix() for f in matches]

        sqlite_matches = [
            f for f in match_names if f.endswith(".sqlite") or f.endswith(".db")
        ]
        for sql_rel in sqlite_matches:
            sql_path = source / sql_rel
            try:
                conn = sqlite3.connect(sql_path)
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                    tables = {row[0].lower() for row in cursor.fetchall()}
                finally:
                    conn.close()
                if any(
                    t in tables
                    for t in (
                        "selections",
                        "compounds",
                        "results",
                        "filtered_compounds",
                    )
                ):
                    return DetectionReport(
                        confidence=0.95,
                        detected_format="smiles2select_sqlite",
                        candidate_files=tuple(match_names),
                        requires_user_mapping=False,
                        suggested_adapter=self.adapter_id,
                    )
            except (OSError, sqlite3.Error):
                continue

        json_or_csv = [
            f
            for f in match_names
            if "smiles2select" in f.lower() or "selection" in f.lower()
        ]
        if json_or_csv:
            return DetectionReport(
                confidence=0.9,
                detected_format="smiles2select_export",
                candidate_files=tuple(match_names),
                requires_user_mapping=False,
                suggested_adapter=self.adapter_id,
            )

        if match_names:
            return DetectionReport(
                confidence=0.4,
                detected_format="possible_smiles2select",
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
        """Build content-addressed import plan for SMILES2Select evidence."""
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
        """Parse compounds, selection decisions, and physicochemical metrics."""
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
                "sqlite"
                if rel_path.endswith((".sqlite", ".db"))
                else ("json" if rel_path.endswith(".json") else "csv")
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

        for rel_path in plan.source_files:
            file_path = source_root / rel_path
            lower_path = rel_path.lower()

            if lower_path.endswith((".sqlite", ".db")):
                compounds.extend(self._parse_sqlite(file_path, rel_path, qc_messages))
            elif lower_path.endswith((".json", ".jsonl")):
                compounds.extend(self._parse_json(file_path, rel_path, qc_messages))
            elif lower_path.endswith((".csv", ".tsv")):
                compounds.extend(self._parse_csv(file_path, rel_path, qc_messages))

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

    def _parse_sqlite(
        self,
        file_path: Path,
        rel_path: str,
        qc_messages: list[QCIssue],
    ) -> list[RawCompoundRecord]:
        records: list[RawCompoundRecord] = []
        try:
            conn = sqlite3.connect(file_path)
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = [row[0] for row in cursor.fetchall()]
                allowed_tables = {
                    "selections",
                    "compounds",
                    "results",
                    "filtered_compounds",
                }
                target_table = next(
                    (t for t in tables if str(t).lower() in allowed_tables), None
                )
                if target_table is None:
                    return records

                # Table names are selected from sqlite_master but still require
                # identifier quoting; values cannot be bound as SQL parameters.
                quoted_table = '"' + str(target_table).replace('"', '""') + '"'
                cursor.execute(f"SELECT * FROM {quoted_table}")
                for row in cursor.fetchall():
                    row_dict = dict(row)
                    cmpd_id = str(
                        row_dict.get("compound_id")
                        or row_dict.get("id")
                        or row_dict.get("name")
                        or f"CMPD_{len(records) + 1}"
                    )
                    smiles = (
                        row_dict.get("smiles")
                        or row_dict.get("canonical_smiles")
                        or row_dict.get("structure")
                    )
                    selected_val = row_dict.get("selected")
                    is_selected = (
                        bool(selected_val) if selected_val is not None else True
                    )

                    meta: dict[str, Any] = {"source_adapter": self.adapter_id}
                    for key, value in row_dict.items():
                        if key.lower() not in (
                            "compound_id",
                            "id",
                            "smiles",
                            "canonical_smiles",
                        ):
                            meta[key] = (
                                bool(value) if key.lower() == "selected" else value
                            )
                    meta["selected"] = is_selected
                    records.append(
                        RawCompoundRecord(
                            source_system="smiles2select",
                            source_value=cmpd_id,
                            source_smiles=str(smiles) if smiles else None,
                            source_artifact_path=rel_path,
                            metadata=meta,
                        )
                    )
            finally:
                conn.close()
        except (OSError, sqlite3.Error) as exc:
            raise ValueError(
                f"SMILES2Select SQLite source '{rel_path}' could not be parsed"
            ) from exc
        return records

    def _parse_json(
        self,
        file_path: Path,
        rel_path: str,
        qc_messages: list[QCIssue],
    ) -> list[RawCompoundRecord]:
        records: list[RawCompoundRecord] = []
        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            items: Any
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("compounds", data.get("results", []))
            else:
                raise ValueError("top-level JSON value must be an array or object")
            if not isinstance(items, list):
                raise ValueError("compound collection must be an array")

            for idx, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    raise ValueError(f"compound row {idx} must be an object")
                cmpd_id = str(
                    item.get("compound_id")
                    or item.get("id")
                    or item.get("name")
                    or f"CMPD_{idx}"
                )
                smiles = item.get("smiles") or item.get("canonical_smiles")
                selected_val = item.get("selected")
                is_selected = bool(selected_val) if selected_val is not None else True

                meta = {
                    "selected": is_selected,
                    "source_adapter": self.adapter_id,
                    **{
                        k: v
                        for k, v in item.items()
                        if k
                        not in (
                            "compound_id",
                            "id",
                            "smiles",
                            "canonical_smiles",
                        )
                    },
                }

                records.append(
                    RawCompoundRecord(
                        source_system="smiles2select",
                        source_value=cmpd_id,
                        source_smiles=str(smiles) if smiles else None,
                        source_artifact_path=rel_path,
                        metadata=meta,
                    )
                )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                f"SMILES2Select JSON source '{rel_path}' could not be parsed"
            ) from exc
        return records

    def _parse_csv(
        self,
        file_path: Path,
        rel_path: str,
        qc_messages: list[QCIssue],
    ) -> list[RawCompoundRecord]:
        records: list[RawCompoundRecord] = []
        try:
            delim = detect_delimiter(file_path)
            with file_path.open(
                mode="r", encoding="utf-8", newline=""
            ) as f:
                reader = csv.DictReader(f, delimiter=delim)
                for idx, row in enumerate(reader, start=1):
                    cmpd_id = str(
                        row.get("compound_id")
                        or row.get("id")
                        or row.get("name")
                        or f"CMPD_{idx}"
                    )
                    smiles = row.get("smiles") or row.get("canonical_smiles")
                    selected_val = row.get("selected")
                    is_selected = (
                        str(selected_val).strip().lower()
                        in ("1", "true", "yes", "selected")
                        if selected_val is not None
                        else True
                    )
                    meta = {
                        "source_adapter": self.adapter_id,
                        **{
                            k: v
                            for k, v in row.items()
                            if k
                            not in (
                                "compound_id",
                                "id",
                                "smiles",
                                "canonical_smiles",
                                "selected",
                            )
                        },
                        "selected": is_selected,
                    }

                    records.append(
                        RawCompoundRecord(
                            source_system="smiles2select",
                            source_value=cmpd_id,
                            source_smiles=str(smiles) if smiles else None,
                            source_artifact_path=rel_path,
                            metadata=meta,
                        )
                    )
        except (OSError, UnicodeError, csv.Error, ValueError) as exc:
            raise ValueError(
                f"SMILES2Select table source '{rel_path}' could not be parsed"
            ) from exc
        return records

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        """Validate parsed SMILES2Select bundle."""
        errors: list[str] = []
        warnings: list[str] = []

        if not bundle.source_artifacts:
            errors.append("Bundle contains no source artifacts")

        if not bundle.compounds:
            errors.append("No compounds were parsed from SMILES2Select evidence")

        return ValidationReport(
            is_valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
            qc_issues=bundle.qc_messages,
        )


__all__ = ["Smiles2SelectAdapter"]
