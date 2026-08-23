"""Unit tests for SMILES2Select adapter probing, planning, and parsing."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fidelichem.adapters.smiles2select.adapter import Smiles2SelectAdapter


def test_smiles2select_probe(tmp_path: Path) -> None:
    adapter = Smiles2SelectAdapter()
    assert adapter.probe(tmp_path).confidence == 0.0

    # JSON selection file
    json_file = tmp_path / "smiles2select_results.json"
    json_file.write_text(
        json.dumps(
            [
                {
                    "compound_id": "SEL_001",
                    "smiles": "CC(=O)Oc1ccccc1C(=O)O",
                    "selected": True,
                    "qed": 0.82,
                    "sa_score": 1.95,
                    "scaffold": "c1ccccc1",
                }
            ]
        ),
        encoding="utf-8",
    )

    report = adapter.probe(tmp_path)
    assert report.confidence >= 0.85
    assert report.suggested_adapter == "fidelichem.smiles2select"


def test_smiles2select_parse_sqlite(tmp_path: Path) -> None:
    adapter = Smiles2SelectAdapter()
    db_file = tmp_path / "smiles2select.sqlite"

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE selections (
            compound_id TEXT PRIMARY KEY,
            smiles TEXT NOT NULL,
            selected INTEGER NOT NULL,
            qed REAL,
            sa_score REAL,
            reason TEXT
        )
        """
    )
    cursor.execute(
        "INSERT INTO selections VALUES (?, ?, ?, ?, ?, ?)",
        (
            "CMPD_1",
            "CC(=O)Oc1ccccc1C(=O)O",
            1,
            0.85,
            2.1,
            "Passed all Lipinski and QED filters",
        ),
    )
    cursor.execute(
        "INSERT INTO selections VALUES (?, ?, ?, ?, ?, ?)",
        (
            "CMPD_2",
            "CCN",
            0,
            0.35,
            4.8,
            "Excluded: low molecular weight",
        ),
    )
    conn.commit()
    conn.close()

    plan = adapter.plan(tmp_path)
    bundle = adapter.parse(plan)

    assert len(bundle.compounds) == 2
    c1 = next(c for c in bundle.compounds if c.source_value == "CMPD_1")
    assert c1.source_smiles == "CC(=O)Oc1ccccc1C(=O)O"
    assert c1.metadata["selected"] is True
    assert c1.metadata["qed"] == 0.85
    assert c1.metadata["sa_score"] == 2.1
    assert "Passed all" in c1.metadata["reason"]

    c2 = next(c for c in bundle.compounds if c.source_value == "CMPD_2")
    assert c2.metadata["selected"] is False
    assert c2.metadata["qed"] == 0.35

    val = adapter.validate(bundle)
    assert val.is_valid


def test_smiles2select_parse_csv_keeps_every_row(tmp_path: Path) -> None:
    adapter = Smiles2SelectAdapter()
    csv_file = tmp_path / "selection.csv"
    csv_file.write_text(
        "compound_id,smiles,selected,qed\n"
        "CMPD_A,CCO,true,0.8\n"
        "CMPD_B,CCN,false,0.4\n",
        encoding="utf-8",
    )

    bundle = adapter.parse(adapter.plan(tmp_path))

    assert [compound.source_value for compound in bundle.compounds] == [
        "CMPD_A",
        "CMPD_B",
    ]
    assert bundle.compounds[0].metadata["selected"] is True
    assert bundle.compounds[1].metadata["selected"] is False
