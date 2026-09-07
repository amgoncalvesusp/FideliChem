"""Acceptance test for multi-format scientific data exports and manifests."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from fidelichem.exports.engine import ExportEngine
from fidelichem.exports.models import ExportFormat, ExportOptions


def test_export_pipeline_with_manifest_and_methods(tmp_path: Path) -> None:
    """Verify export bundle creation, file integrity, and manifest."""
    engine = ExportEngine()

    records = [
        {
            "compound_id": "CMPD_01",
            "smiles": "c1ccccc1NC(=O)C",
            "gold_score": 78.5,
            "chemplp": 85.2,
            "consensus_percentile": 0.94,
            "priority": "ADVANCE",
        },
        {
            "compound_id": "CMPD_02",
            "smiles": "c1cccnc1",
            "gold_score": 65.0,
            "chemplp": 70.1,
            "consensus_percentile": 0.72,
            "priority": "HOLD",
        },
    ]

    options = ExportOptions(
        formats=(
            ExportFormat.CSV,
            ExportFormat.JSON,
            ExportFormat.XLSX,
            ExportFormat.METHODS_REPORT,
        )
    )

    parameters = {
        "score_normalizer": "percentile (higher_better=1.0)",
        "pose_rmsd_cutoff": 2.0,
        "decision_profile": "kinase_profile_v1",
    }

    out_dir = tmp_path / "screening_exports"
    result = engine.export_dataset(
        project_name="KinaseScreening",
        records=records,
        output_dir=out_dir,
        options=options,
        parameters=parameters,
    )

    assert Path(result.manifest_path).exists()
    assert result.total_records == 2
    assert len(result.files) == 5  # CSV, JSON, XLSX, METHODS_REPORT, manifest.json

    manifest_data = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest_data["project_name"] == "KinaseScreening"
    assert len(manifest_data["exported_files"]) == 4

    for record in manifest_data["exported_files"]:
        fpath = out_dir / record["relative_path"]
        assert fpath.exists()
        actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert actual_sha == record["sha256"]


def test_export_options_filter_persisted_evidence_without_mutating_snapshot(
    tmp_path: Path,
) -> None:
    records = [
        {"evidence_type": "target", "name": "Target A", "import_batch_id": "b1"},
        {
            "evidence_type": "score",
            "score_key": "fitness",
            "raw_value": -7.2,
            "import_batch_id": "b1",
        },
        {
            "evidence_type": "interaction",
            "interaction_type": "hbond",
            "import_batch_id": "b1",
        },
        {"evidence_type": "md_run", "run_name": "md-1", "import_batch_id": "b1"},
    ]
    original = [dict(record) for record in records]

    result = ExportEngine().export_dataset(
        project_name="Filtered",
        records=records,
        output_dir=tmp_path,
        options=ExportOptions(
            formats=(ExportFormat.JSON,),
            include_scores=False,
            include_interactions=False,
            include_dynamics=False,
            include_provenance=False,
        ),
    )

    exported = json.loads(
        (tmp_path / "Filtered_candidates.json").read_text(encoding="utf-8")
    )
    assert result.total_records == 1
    assert exported == [{"evidence_type": "target", "name": "Target A"}]
    assert records == original


def test_mixed_evidence_survives_excel_and_csv_with_manifest(tmp_path: Path) -> None:
    import openpyxl

    records = [
        {"evidence_type": "target", "name": "Target A"},
        {"evidence_type": "score", "raw_value": -7.2, "score_key": "vina"},
        {"evidence_type": "md_run", "parameters": {"seed": 42}},
    ]
    original = json.dumps(records)
    result = ExportEngine().export_dataset(
        project_name="Mixed",
        records=records,
        output_dir=tmp_path,
        options=ExportOptions(formats=(ExportFormat.CSV, ExportFormat.XLSX)),
    )
    with (tmp_path / "Mixed_candidates.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert rows[1]["raw_value"] == "-7.2"
    assert json.loads(rows[2]["parameters"]) == {"seed": 42}
    workbook = openpyxl.load_workbook(tmp_path / "Mixed_candidates.xlsx")
    headers, *values = list(workbook.active.values)
    xlsx_rows = [dict(zip(headers, row, strict=True)) for row in values]
    assert xlsx_rows[1]["raw_value"] == -7.2
    assert xlsx_rows[0]["raw_value"] is None
    workbook.close()
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    for artifact in manifest["exported_files"]:
        assert (
            hashlib.sha256(
                (tmp_path / artifact["relative_path"]).read_bytes()
            ).hexdigest()
            == artifact["sha256"]
        )
    assert json.dumps(records) == original
