"""Unit tests for scientific data exporters, manifests, and methods reports."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from fidelichem.exports.engine import ExportEngine
from fidelichem.exports.models import ExportFormat, ExportOptions
from fidelichem.exports.reports import generate_methods_report
from fidelichem.exports.tabular import (
    export_to_csv,
    export_to_json,
    export_to_parquet,
    export_to_xlsx,
)


def test_export_to_csv_and_json(tmp_path: Path) -> None:
    records = [
        {"compound_id": "C01", "docking_score": 78.5, "priority": "ADVANCE"},
        {"compound_id": "C02", "docking_score": 62.1, "priority": "HOLD"},
    ]

    csv_path = tmp_path / "compounds.csv"
    res_csv = export_to_csv(records, csv_path)
    assert res_csv.exists()
    content = csv_path.read_text(encoding="utf-8")
    assert "C01" in content
    assert "ADVANCE" in content

    json_path = tmp_path / "compounds.json"
    res_json = export_to_json(records, json_path)
    assert res_json.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(loaded) == 2
    assert loaded[0]["compound_id"] == "C01"


def test_export_to_xlsx(tmp_path: Path) -> None:
    records = [
        {"compound_id": "C01", "docking_score": 78.5, "priority": "ADVANCE"},
    ]
    xlsx_path = tmp_path / "compounds.xlsx"
    res_xlsx = export_to_xlsx(records, xlsx_path)
    assert res_xlsx.exists()
    assert res_xlsx.stat().st_size > 0


def test_xlsx_fallback_escapes_xml_content(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "compounds.xlsx"
    export_to_xlsx(
        [{"compound_id": "C&<1", "note": "<unsafe>&"}],
        xlsx_path,
    )

    # The dependency-free SpreadsheetML fallback must remain well-formed.
    ElementTree.parse(xlsx_path)


def test_parquet_fallback_returns_actual_csv_path(tmp_path: Path) -> None:
    parquet_path = tmp_path / "compounds.parquet"
    result = export_to_parquet([{"compound_id": "C01"}], parquet_path)

    assert result == tmp_path / "compounds.csv"
    assert result.exists()
    assert not parquet_path.exists()


def test_export_engine_keeps_project_name_inside_output_directory(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "exports"
    result = ExportEngine().export_dataset(
        project_name="../outside/report",
        records=({"compound_id": "C01"},),
        output_dir=output_dir,
        options=ExportOptions(formats=(ExportFormat.CSV,)),
    )

    resolved_output = output_dir.resolve()
    assert all(
        Path(file_path).resolve().is_relative_to(resolved_output)
        for file_path in result.files
    )
    assert (output_dir / "outside_report_candidates.csv").is_file()


def test_generate_methods_report(tmp_path: Path) -> None:
    report_path = tmp_path / "METHODS_REPORT.md"
    params = {
        "score_normalizer": "percentile (better=1.0)",
        "pose_consensus_cutoff_angstrom": 2.0,
        "interaction_consensus_threshold": 0.75,
        "decision_profile": "beta_lactamase_screening_v1",
    }
    res = generate_methods_report(
        project_name="BetaLactamaseProject",
        parameters=params,
        output_path=report_path,
    )
    assert res.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "BetaLactamaseProject" in content
    assert "Methods & Reproducibility Report" in content
    assert "2.0" in content
    assert "0.75" in content
