"""Unit tests for GoldAdapter probing, planning, parsing, and QC diagnostics."""

from __future__ import annotations

from pathlib import Path

from fidelichem.adapters.gold.adapter import GoldAdapter


def test_gold_adapter_probe_and_confidence(tmp_path: Path) -> None:
    adapter = GoldAdapter()

    # Empty dir
    assert adapter.probe(tmp_path).confidence == 0.0

    # Directory with gold.conf and bestranking.lst
    (tmp_path / "gold.conf").write_text(
        "protein_datafile = /path/to/target_ctx.pdb\n",
        encoding="utf-8",
    )
    (tmp_path / "bestranking.lst").write_text(
        "Rank\tFile\tChemPLP\tLigand\n1\tsoln.mol2\t85.0\tL1\n",
        encoding="utf-8",
    )

    report = adapter.probe(tmp_path)
    assert report.confidence >= 0.9
    assert report.suggested_adapter == "fidelichem.gold"
    assert "gold.conf" in report.candidate_files
    assert "bestranking.lst" in report.candidate_files


def test_gold_adapter_parse_complete_run(tmp_path: Path) -> None:
    adapter = GoldAdapter()

    # Setup complete GOLD directory
    (tmp_path / "gold.conf").write_text(
        "protein_datafile = /path/to/receptor_kras.pdb\n"
        "fitness_function = CHEMPLP\n"
        "rescore_function = GOLDSCORE\n",
        encoding="utf-8",
    )

    (tmp_path / "bestranking.lst").write_text(
        "Rank\tSolution_File\tChemPLP\tGoldScore\tLigand_Name\n"
        "1\tgold_soln_lig1_m1_1.mol2\t92.40\t78.10\tLIG_101\n"
        "2\tgold_soln_lig1_m1_2.mol2\t84.20\t71.50\tLIG_101\n"
        "3\tgold_soln_lig2_m1_1.mol2\t76.00\t64.00\tLIG_102\n",
        encoding="utf-8",
    )

    # MOL2 solutions
    mol2_tmpl = (
        "@<TRIPOS>MOLECULE\n{name}\n 1 0 0 0 0\n"
        "SMALL\nNO_CHARGES\n@<TRIPOS>ATOM\n 1 C1 {x} 0 0 C.3 1 LIG 0.0\n"
    )
    (tmp_path / "gold_soln_lig1_m1_1.mol2").write_text(
        mol2_tmpl.format(name="LIG_101", x=0),
        encoding="utf-8",
    )
    (tmp_path / "gold_soln_lig1_m1_2.mol2").write_text(
        mol2_tmpl.format(name="LIG_101", x=1),
        encoding="utf-8",
    )
    (tmp_path / "gold_soln_lig2_m1_1.mol2").write_text(
        mol2_tmpl.format(name="LIG_102", x=2),
        encoding="utf-8",
    )

    plan = adapter.plan(tmp_path)
    assert plan.adapter_id == "fidelichem.gold"

    bundle = adapter.parse(plan)
    assert len(bundle.targets) == 1
    assert bundle.targets[0].name == "receptor_kras"

    assert len(bundle.docking_runs) == 1
    assert bundle.docking_runs[0].engine == "GOLD"

    assert len(bundle.compounds) == 2
    compound_names = {c.source_value for c in bundle.compounds}
    assert compound_names == {"LIG_101", "LIG_102"}

    assert len(bundle.poses) == 3
    assert len(bundle.scores) == 6  # 3 ChemPLP + 3 GoldScore

    val = adapter.validate(bundle)
    assert val.is_valid


def test_gold_adapter_qc_detects_missing_solution_file(tmp_path: Path) -> None:
    adapter = GoldAdapter()

    (tmp_path / "gold.conf").write_text(
        "protein_datafile = target.pdb\n",
        encoding="utf-8",
    )
    (tmp_path / "bestranking.lst").write_text(
        "Rank\tSolution_File\tChemPLP\tLigand_Name\n"
        "1\tmissing_soln.mol2\t90.00\tLIG_MISSING\n",
        encoding="utf-8",
    )

    plan = adapter.plan(tmp_path)
    bundle = adapter.parse(plan)

    assert any("QC_MISSING_SOLUTION" in qc.code for qc in bundle.qc_messages)
