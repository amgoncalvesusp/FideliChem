"""Regression coverage for heterogeneous evidence and Excel text integrity."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import openpyxl
import pytest

from fidelichem.exports.tabular import export_to_csv, export_to_parquet, export_to_xlsx


@pytest.fixture
def evidence():
    return [
        {"evidence_type": "target", "name": "Target A"},
        {"evidence_type": "score", "raw_value": -7.4, "score_key": "vina_affinity"},
        {"evidence_type": "interaction", "distance": 2.8, "metadata": {"chain": "A"}},
    ]


def test_csv_keeps_fields_from_all_evidence_families(tmp_path, evidence):
    path = export_to_csv(evidence, tmp_path / "evidence.csv")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[1]["raw_value"] == "-7.4"
    assert rows[0]["raw_value"] == ""
    assert json.loads(rows[2]["metadata"]) == {"chain": "A"}


def test_xlsx_keeps_fields_from_all_evidence_families(tmp_path, evidence):
    path = export_to_xlsx(evidence, tmp_path / "evidence.xlsx")
    workbook = openpyxl.load_workbook(path)
    headers, *values = list(workbook.active.values)
    rows = [dict(zip(headers, row, strict=True)) for row in values]
    assert rows[1]["raw_value"] == -7.4
    assert rows[0]["raw_value"] is None
    assert json.loads(rows[2]["metadata"]) == {"chain": "A"}
    workbook.close()


def test_xlsx_preserves_literal_formulas_and_escapes_invalid_xml(tmp_path):
    path = export_to_xlsx(
        [{"=header": "=1+1", "note": "A\x01B\ufffeC", "parameters": {"seed": 42}}],
        tmp_path / "text.xlsx",
    )
    workbook = openpyxl.load_workbook(path)
    sheet = workbook.active
    assert sheet["A1"].data_type == "s"
    assert sheet["A2"].data_type == "s"
    assert sheet["A2"].value == "=1+1"
    assert sheet["B2"].value == r"A\u0001B\ufffeC"
    assert json.loads(sheet["C2"].value) == {"seed": 42}
    workbook.close()


def test_xlsx_rejects_silent_excel_text_truncation(tmp_path):
    with pytest.raises(ValueError, match="32767"):
        export_to_xlsx([{"note": "a" * 32768}], tmp_path / "long.xlsx")


def test_parquet_preserves_heterogeneous_schema(tmp_path, evidence):
    parquet = pytest.importorskip("pyarrow.parquet")
    path = export_to_parquet(evidence, tmp_path / "evidence.parquet")
    rows = parquet.read_table(path).to_pylist()
    assert rows[1]["raw_value"] == -7.4
    assert rows[0]["raw_value"] is None
    assert rows[2]["metadata"] == {"chain": "A"}


def test_explicit_csv_columns_remain_an_intentional_projection(tmp_path: Path):
    path = export_to_csv([{"a": 1, "b": 2}], tmp_path / "selected.csv", ["b"])
    assert path.read_text(encoding="utf-8").splitlines() == ["b", "2"]
