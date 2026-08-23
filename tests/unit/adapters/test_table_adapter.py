"""Unit tests for UniversalTableAdapter parsing and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from fidelichem.adapters.table.adapter import UniversalTableAdapter
from fidelichem.domain.table_importer import (
    IdentityColumnMapping,
    ScoreColumnMapping,
    ScoreDirection,
    TableMappingSchema,
)


def test_table_adapter_probe(tmp_path: Path) -> None:
    adapter = UniversalTableAdapter()

    # Empty directory
    empty_report = adapter.probe(tmp_path)
    assert empty_report.confidence == 0.0

    # Directory with CSV
    csv_file = tmp_path / "screen.csv"
    csv_file.write_text("id,smiles,score\nL1,CCO,-5.0\n", encoding="utf-8")

    report = adapter.probe(tmp_path)
    assert report.confidence >= 0.8
    assert report.suggested_adapter == "fidelichem.universal_table"
    assert "screen.csv" in report.candidate_files
    assert report.requires_user_mapping is True


def test_table_adapter_supports_txt_and_infers_identity_columns(tmp_path: Path) -> None:
    adapter = UniversalTableAdapter()
    text_file = tmp_path / "screen.txt"
    text_file.write_text(
        "access_code\tsmiles\nEOS001\tCCO\nEOS002\tCCN\n",
        encoding="utf-8",
    )

    report = adapter.probe(text_file)
    assert report.confidence >= 0.8
    assert report.detected_format == "tabular"

    bundle = adapter.parse(adapter.plan(text_file))
    assert [compound.source_value for compound in bundle.compounds] == [
        "EOS001",
        "EOS002",
    ]
    assert [compound.source_smiles for compound in bundle.compounds] == ["CCO", "CCN"]


def test_table_adapter_reads_xlsx_with_blank_trailing_headers(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(["access_code", "smiles", None, None])
    worksheet.append(["EOS001", "CCO", "unused", 1.0])
    source = tmp_path / "screen.xlsx"
    workbook.save(source)
    workbook.close()

    bundle = UniversalTableAdapter().parse(UniversalTableAdapter().plan(source))
    assert len(bundle.compounds) == 1
    assert bundle.compounds[0].source_value == "EOS001"
    assert bundle.compounds[0].source_smiles == "CCO"


def test_table_adapter_parse_csv_with_schema(tmp_path: Path) -> None:
    adapter = UniversalTableAdapter()
    csv_file = tmp_path / "compounds_scores.csv"
    csv_file.write_text(
        "Ligand_ID,Canonical_SMILES,Docking_Score,MW\n"
        "CMPD_01,CC(=O)Oc1ccccc1C(=O)O,-9.2,180.16\n"
        "CMPD_02,c1ccccc1,-5.1,78.11\n"
        "CMPD_03,CCN,,45.08\n",  # Missing score on row 3
        encoding="utf-8",
    )

    schema = TableMappingSchema(
        identity=IdentityColumnMapping(
            molecule_id_column="Ligand_ID",
            smiles_column="Canonical_SMILES",
            source_system_default="custom_lab",
            target_name_default="Target_Beta",
            run_name_default="Vina_Run_1",
        ),
        scores=(
            ScoreColumnMapping(
                column_name="Docking_Score",
                score_key="vina.score",
                direction=ScoreDirection.LOWER_BETTER,
            ),
        ),
        property_columns=("MW",),
    )

    plan = adapter.plan(tmp_path, options={"schema": schema.model_dump(mode="json")})
    assert plan.adapter_id == "fidelichem.universal_table"

    bundle = adapter.parse(plan)
    assert len(bundle.compounds) == 3
    assert bundle.compounds[0].source_system == "custom_lab"
    assert bundle.compounds[0].source_value == "CMPD_01"
    assert bundle.compounds[0].source_smiles == "CC(=O)Oc1ccccc1C(=O)O"

    # Verify scores: only rows 1 and 2 had scores; row 3 must NOT have score
    # (invariant: missing data is preserved as None)
    assert len(bundle.scores) == 2

    assert bundle.scores[0].compound_source_value == "CMPD_01"
    assert bundle.scores[0].score_key == "vina.score"
    assert bundle.scores[0].raw_value == -9.2

    assert bundle.scores[1].compound_source_value == "CMPD_02"
    assert bundle.scores[1].raw_value == -5.1

    # Validation
    val_report = adapter.validate(bundle)
    assert val_report.is_valid


def test_table_adapter_handles_unparseable_scores_gracefully(tmp_path: Path) -> None:
    adapter = UniversalTableAdapter()
    csv_file = tmp_path / "bad_scores.csv"
    csv_file.write_text(
        "id,smiles,score\nL1,CCO,INVALID_NUMBER\n",
        encoding="utf-8",
    )

    schema = TableMappingSchema(
        identity=IdentityColumnMapping(molecule_id_column="id", smiles_column="smiles"),
        scores=(ScoreColumnMapping(column_name="score", score_key="test.score"),),
    )

    plan = adapter.plan(tmp_path, options={"schema": schema.model_dump(mode="json")})
    bundle = adapter.parse(plan)

    assert len(bundle.compounds) == 1
    assert len(bundle.scores) == 0  # Invalid score skipped
    assert len(bundle.qc_messages) >= 1
    assert any("INVALID_SCORE" in m.code for m in bundle.qc_messages)
