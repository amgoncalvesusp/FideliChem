"""Acceptance test for multi-format scientific data exports and manifests."""

from __future__ import annotations

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
