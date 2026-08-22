"""Unit tests for scientific data exporters, manifests, and methods reports."""

from __future__ import annotations

import json
from pathlib import Path

from fidelichem.exports.reports import generate_methods_report
from fidelichem.exports.tabular import (
    export_to_csv,
    export_to_json,
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
