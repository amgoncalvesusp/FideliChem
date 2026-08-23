"""Unit tests for SMILES2Docking ligand preparation adapter."""

from __future__ import annotations

import json
from pathlib import Path

from fidelichem.adapters.smiles2docking.adapter import Smiles2DockingAdapter


def test_smiles2docking_probe(tmp_path: Path) -> None:
    adapter = Smiles2DockingAdapter()
    assert adapter.probe(tmp_path).confidence == 0.0

    # Create preparation run JSON
    run_file = tmp_path / "smiles2docking_run.json"
    run_file.write_text(
        json.dumps(
            {
                "run_id": "prep_run_01",
                "target_ph": 7.4,
                "protonation_engine": "dimorphite-dl",
                "optimization_method": "ETKDG+MMFF94",
                "compounds": [
                    {
                        "compound_id": "PREP_LIG_01",
                        "initial_smiles": "CC(=O)Oc1ccccc1C(=O)O",
                        "protonated_smiles": "CC(=O)Oc1ccccc1C(=O)[O-]",
                        "structure_file": "prep_lig_01.sdf",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = adapter.probe(tmp_path)
    assert report.confidence >= 0.85
    assert report.suggested_adapter == "fidelichem.smiles2docking"


def test_smiles2docking_parses_prepared_mol2_with_embedded_smiles(
    tmp_path: Path,
) -> None:
    adapter = Smiles2DockingAdapter()
    (tmp_path / "prepared_ligands.mol2").write_text(
        "@<TRIPOS>MOLECULE\n"
        "EOS001\n"
        " 1 0 0 0 0\n"
        "SMALL\nNO_CHARGES\n\n"
        "> <SMILES>\nCCO\n\n"
        "@<TRIPOS>ATOM\n"
        " 1 C1 0.0 0.0 0.0 C.3 1 LIG 0.0\n",
        encoding="utf-8",
    )

    report = adapter.probe(tmp_path)
    assert report.confidence >= 0.75
    bundle = adapter.parse(adapter.plan(tmp_path))
    assert len(bundle.compounds) == 1
    assert bundle.compounds[0].source_value == "EOS001"
    assert bundle.compounds[0].source_smiles == "CCO"


def test_smiles2docking_single_structure_includes_sibling_report(
    tmp_path: Path,
) -> None:
    """Choosing one MOL2 file must retain the adjacent run metadata."""
    adapter = Smiles2DockingAdapter()
    mol2 = tmp_path / "prepared_ligands.mol2"
    mol2.write_text(
        "@<TRIPOS>MOLECULE\n"
        "LIG_01\n"
        " 1 0 0 0 0\n"
        "SMALL\nNO_CHARGES\n\n"
        "@<TRIPOS>ATOM\n"
        " 1 C1 0.0 0.0 0.0 C.3 1 LIG 0.0\n",
        encoding="utf-8",
    )
    report = tmp_path / "run_report_20260101T000000Z.json"
    report.write_text(
        json.dumps(
            {
                "compounds": [
                    {
                        "compound_id": "LIG_01",
                        "state_smiles": "CCO",
                        "structure_file": mol2.name,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    detection = adapter.probe(mol2)
    assert detection.confidence == 0.95
    assert mol2.name in detection.candidate_files
    assert report.name in detection.candidate_files

    bundle = adapter.parse(adapter.plan(mol2))
    assert len(bundle.compounds) == 1
    assert bundle.compounds[0].source_smiles == "CCO"


def test_smiles2docking_parse_run(tmp_path: Path) -> None:
    adapter = Smiles2DockingAdapter()

    run_file = tmp_path / "run.json"
    run_file.write_text(
        json.dumps(
            {
                "run_id": "dockprep_egfr",
                "target_ph": 7.4,
                "protonation_engine": "dimorphite-dl",
                "optimization_method": "PM7",
                "compounds": [
                    {
                        "compound_id": "ASPIRIN_PREP",
                        "initial_smiles": "CC(=O)Oc1ccccc1C(=O)O",
                        "state_smiles": "CC(=O)Oc1ccccc1C(=O)[O-]",
                        "structure_file": "aspirin_prep.sdf",
                    },
                    {
                        "compound_id": "PARACETAMOL_PREP",
                        "initial_smiles": "CC(=O)Nc1ccc(O)cc1",
                        "state_smiles": "CC(=O)Nc1ccc(O)cc1",
                        "structure_file": "paracetamol_prep.sdf",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    (tmp_path / "aspirin_prep.sdf").write_text("$$$$\n", encoding="utf-8")
    (tmp_path / "paracetamol_prep.sdf").write_text("$$$$\n", encoding="utf-8")

    plan = adapter.plan(tmp_path)
    bundle = adapter.parse(plan)

    assert len(bundle.compounds) == 2
    c1 = next(c for c in bundle.compounds if c.source_value == "ASPIRIN_PREP")
    assert c1.preparation_ph == 7.4
    assert c1.source_smiles == "CC(=O)Oc1ccccc1C(=O)[O-]"
    assert c1.metadata["protonation_engine"] == "dimorphite-dl"
    assert c1.metadata["optimization_method"] == "PM7"

    val = adapter.validate(bundle)
    assert val.is_valid
