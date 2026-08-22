"""Unit tests for DockLens mechanistic interaction adapter."""

from __future__ import annotations

import json
from pathlib import Path

from fidelichem.adapters.docklens.adapter import DockLensAdapter


def test_docklens_probe(tmp_path: Path) -> None:
    adapter = DockLensAdapter()
    assert adapter.probe(tmp_path).confidence == 0.0

    json_file = tmp_path / "docklens_interactions.json"
    json_file.write_text(
        json.dumps(
            {
                "run_name": "gold_run_egfr",
                "target_name": "EGFR",
                "interactions": [
                    {
                        "compound_id": "LIG_01",
                        "pose_id": "gold_soln_lig_01_m1_1",
                        "residue": "MET793",
                        "interaction_type": "hydrogen_bond",
                        "distance": 2.05,
                        "angle": 168.0,
                        "occupancy": 1.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = adapter.probe(tmp_path)
    assert report.confidence >= 0.85
    assert report.suggested_adapter == "fidelichem.docklens"


def test_docklens_parse_json(tmp_path: Path) -> None:
    adapter = DockLensAdapter()
    json_file = tmp_path / "docklens_export.json"
    json_file.write_text(
        json.dumps(
            {
                "run_name": "gold_docking_egfr",
                "target_name": "EGFR",
                "interactions": [
                    {
                        "compound_id": "ERLOTINIB",
                        "pose_id": "P001",
                        "residue": "MET793",
                        "interaction_type": "hydrogen_bond",
                        "distance": 2.12,
                        "angle": 164.5,
                        "occupancy": 1.0,
                        "ligand_feature": "N1_quinazoline",
                    },
                    {
                        "compound_id": "ERLOTINIB",
                        "pose_id": "P001",
                        "residue": "LEU718",
                        "interaction_type": "hydrophobic",
                        "distance": 3.75,
                        "occupancy": 0.92,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    plan = adapter.plan(tmp_path)
    bundle = adapter.parse(plan)

    assert len(bundle.interactions) == 2
    i1 = bundle.interactions[0]
    assert i1.run_name == "gold_docking_egfr"
    assert i1.compound_source_value == "ERLOTINIB"
    assert i1.source_pose_id == "P001"
    assert i1.residue_name == "MET793"
    assert i1.interaction_type == "hydrogen_bond"
    assert i1.distance == 2.12
    assert i1.angle == 164.5
    assert i1.interaction_key == "EGFR|MET793|hydrogen_bond"
    assert i1.granular_interaction_key == "EGFR|MET793|hydrogen_bond|N1_quinazoline"

    i2 = bundle.interactions[1]
    assert i2.interaction_key == "EGFR|LEU718|hydrophobic"
    assert i2.granular_interaction_key == "EGFR|LEU718|hydrophobic|any"

    val = adapter.validate(bundle)
    assert val.is_valid
