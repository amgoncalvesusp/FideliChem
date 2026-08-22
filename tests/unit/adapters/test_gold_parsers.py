"""Unit tests for CCDC GOLD file parsers (gold.conf, ranking, mol2)."""

from __future__ import annotations

from pathlib import Path

from fidelichem.adapters.gold.parsers import (
    parse_gold_conf,
    parse_gold_mol2,
    parse_gold_ranking,
)


def test_parse_gold_conf(tmp_path: Path) -> None:
    conf_file = tmp_path / "gold.conf"
    conf_file.write_text(
        "GOLD CONFIGURATION FILE\n"
        "protein_datafile = /data/structures/receptor_ctx_m_15.pdb\n"
        "fitness_function = CHEMPLP\n"
        "rescore_function = GOLDSCORE\n"
        "early_termination = 1\n"
        "autoscale = 1.0\n",
        encoding="utf-8",
    )

    conf = parse_gold_conf(conf_file)
    assert conf["target_name"] == "receptor_ctx_m_15"
    assert conf["fitness_function"] == "CHEMPLP"
    assert conf["rescore_function"] == "GOLDSCORE"
    assert conf["params"]["early_termination"] == "1"


def test_parse_gold_ranking_bestranking_lst(tmp_path: Path) -> None:
    ranking_file = tmp_path / "bestranking.lst"
    ranking_file.write_text(
        "# GOLD Ranking List\n"
        "Rank\tSolution_File\tChemPLP\tGoldScore\tLigand_Name\n"
        "1\tgold_soln_m1_m1_1.mol2\t86.42\t72.10\tLIG_01\n"
        "2\tgold_soln_m1_m1_2.mol2\t79.15\t68.40\tLIG_01\n"
        "3\tgold_soln_m2_m1_1.mol2\t65.80\t55.20\tLIG_02\n",
        encoding="utf-8",
    )

    rows = parse_gold_ranking(ranking_file)
    assert len(rows) == 3
    assert rows[0]["rank"] == 1
    assert rows[0]["solution_file"] == "gold_soln_m1_m1_1.mol2"
    assert rows[0]["ligand_name"] == "LIG_01"
    assert rows[0]["scores"]["gold.chemplp"] == 86.42
    assert rows[0]["scores"]["gold.goldscore"] == 72.10


def test_parse_gold_mol2_solutions(tmp_path: Path) -> None:
    mol2_file = tmp_path / "gold_soln_m1_m1_1.mol2"
    mol2_file.write_text(
        "@<TRIPOS>MOLECULE\n"
        "LIG_01\n"
        " 3 2 0 0 0\n"
        "SMALL\n"
        "USER_CHARGES\n"
        "> <Gold.Score>\n"
        "72.10\n"
        "> <ChemPLP.Fitness>\n"
        "86.42\n"
        "> <ASP.Fitness>\n"
        "45.30\n"
        "@<TRIPOS>ATOM\n"
        " 1 C1 0.000 0.000 0.000 C.3 1 LIG 0.0\n"
        " 2 C2 1.000 0.000 0.000 C.3 1 LIG 0.0\n"
        " 3 O1 2.000 0.000 0.000 O.3 1 LIG 0.0\n"
        "@<TRIPOS>BOND\n"
        " 1 1 2 1\n"
        " 2 2 3 1\n",
        encoding="utf-8",
    )

    poses = parse_gold_mol2(mol2_file)
    assert len(poses) == 1
    p1 = poses[0]
    assert p1["ligand_name"] == "LIG_01"
    assert p1["scores"]["gold.chemplp"] == 86.42
    assert p1["scores"]["gold.goldscore"] == 72.10
    assert p1["scores"]["gold.asp"] == 45.30
    assert p1["atom_count"] == 3
