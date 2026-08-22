"""Unit tests for MolDynStudio molecular dynamics adapter."""

from __future__ import annotations

import json
from pathlib import Path

from fidelichem.adapters.moldynstudio.adapter import MolDynStudioAdapter


def test_moldynstudio_probe(tmp_path: Path) -> None:
    adapter = MolDynStudioAdapter()
    assert adapter.probe(tmp_path).confidence == 0.0

    (tmp_path / "fidelichem-md-result-v1.json").write_text(
        json.dumps(
            {
                "run_name": "md_sim_egfr_erlotinib",
                "duration_ns": 100.0,
                "temperature_k": 300.0,
                "timestep_fs": 2.0,
                "target_name": "EGFR",
                "compound_id": "ERLOTINIB",
                "metrics": [
                    {
                        "metric_key": "rmsd_backbone",
                        "mean": 0.18,
                        "std": 0.03,
                        "min": 0.05,
                        "max": 0.22,
                        "unit": "nm",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = adapter.probe(tmp_path)
    assert report.confidence >= 0.90
    assert report.suggested_adapter == "fidelichem.moldynstudio"


def test_moldynstudio_parse_json(tmp_path: Path) -> None:
    adapter = MolDynStudioAdapter()
    (tmp_path / "moldynstudio_report.json").write_text(
        json.dumps(
            {
                "run_name": "md_sim_01",
                "duration_ns": 50.0,
                "temperature_k": 310.0,
                "timestep_fs": 2.0,
                "target_name": "EGFR",
                "compound_id": "CMPD_01",
                "pose_id": "P001",
                "metrics": [
                    {
                        "metric_key": "rmsd_ligand",
                        "mean": 0.12,
                        "std": 0.02,
                        "min": 0.04,
                        "max": 0.15,
                        "unit": "nm",
                    },
                    {
                        "metric_key": "hbond_occupancy",
                        "mean": 0.85,
                        "std": 0.10,
                        "unit": "fraction",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    plan = adapter.plan(tmp_path)
    bundle = adapter.parse(plan)

    assert len(bundle.md_runs) == 1
    run = bundle.md_runs[0]
    assert run.run_name == "md_sim_01"
    assert run.duration_ns == 50.0
    assert run.temperature_k == 310.0
    assert run.target_name == "EGFR"
    assert run.compound_source_value == "CMPD_01"
    assert run.source_pose_id == "P001"

    assert len(bundle.md_metrics) == 2
    m1 = next(m for m in bundle.md_metrics if m.metric_key == "rmsd_ligand")
    assert m1.mean_value == 0.12
    assert m1.unit == "nm"

    val = adapter.validate(bundle)
    assert val.is_valid
