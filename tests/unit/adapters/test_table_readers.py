"""Unit tests for tabular file readers and format detection."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fidelichem.adapters.table.readers import (
    detect_delimiter,
    detect_format,
    preview_table,
    read_table_records,
)
from fidelichem.domain.table_importer import (
    IdentityColumnMapping,
    TableMappingSchema,
)


def test_detect_format_by_extension_and_content(tmp_path: Path) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    assert detect_format(csv_file) == "csv"

    tsv_file = tmp_path / "data.tsv"
    tsv_file.write_text("a\tb\tc\n1\t2\t3\n", encoding="utf-8")
    assert detect_format(tsv_file) == "tsv"

    json_file = tmp_path / "data.json"
    json_file.write_text('[{"a": 1, "b": 2}]', encoding="utf-8")
    assert detect_format(json_file) == "json"

    jsonl_file = tmp_path / "data.jsonl"
    jsonl_file.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
    assert detect_format(jsonl_file) == "jsonl"


def test_detect_delimiter_and_preview(tmp_path: Path) -> None:
    # Comma CSV
    csv_file = tmp_path / "sample_comma.csv"
    csv_file.write_text(
        "id,smiles,score\nL1,CC(=O)O,-8.5\nL2,c1ccccc1,-6.2\n", encoding="utf-8"
    )
    assert detect_delimiter(csv_file) == ","

    headers, rows = preview_table(csv_file, max_rows=2)
    assert headers == ("id", "smiles", "score")
    assert len(rows) == 2
    assert rows[0] == ("L1", "CC(=O)O", "-8.5")

    # Semicolon CSV
    semi_file = tmp_path / "sample_semi.csv"
    semi_file.write_text("id;smiles;score\nL1;CC(=O)O;-8.5\n", encoding="utf-8")
    assert detect_delimiter(semi_file) == ";"

    headers_semi, rows_semi = preview_table(semi_file, max_rows=5)
    assert headers_semi == ("id", "smiles", "score")
    assert len(rows_semi) == 1

    # TSV
    tsv_file = tmp_path / "sample.tsv"
    tsv_file.write_text("id\tsmiles\tscore\nL1\tCC(=O)O\t-8.5\n", encoding="utf-8")
    assert detect_delimiter(tsv_file) == "\t"

    headers_tsv, rows_tsv = preview_table(tsv_file)
    assert headers_tsv == ("id", "smiles", "score")
    assert len(rows_tsv) == 1


def test_preview_json_and_jsonl(tmp_path: Path) -> None:
    # JSON list of dicts
    json_file = tmp_path / "dataset.json"
    json_file.write_text(
        json.dumps([{"id": "L1", "smiles": "CCO", "score": -5.5}]),
        encoding="utf-8",
    )
    headers_j, rows_j = preview_table(json_file)
    assert headers_j == ("id", "score", "smiles") or set(headers_j) == {
        "id",
        "smiles",
        "score",
    }
    assert len(rows_j) == 1

    # JSONL
    jsonl_file = tmp_path / "dataset.jsonl"
    jsonl_file.write_text(
        '{"id": "L1", "smiles": "CCO"}\n{"id": "L2", "smiles": "CCN"}\n',
        encoding="utf-8",
    )
    headers_jl, rows_jl = preview_table(jsonl_file)
    assert set(headers_jl) == {"id", "smiles"}
    assert len(rows_jl) == 2


def test_read_table_records_preserves_missing_data(tmp_path: Path) -> None:
    csv_file = tmp_path / "missing_data.csv"
    csv_file.write_text(
        "id,smiles,score,notes\n"
        "L1,CCO,-7.2,active\n"
        "L2,c1ccccc1,,\n"  # Missing score and notes
        "L3,CCN,NA,   \n",  # NA score and whitespace notes
        encoding="utf-8",
    )

    schema = TableMappingSchema(
        identity=IdentityColumnMapping(molecule_id_column="id", smiles_column="smiles"),
        delimiter=",",
    )

    records = list(read_table_records(csv_file, schema))
    assert len(records) == 3

    assert records[0]["id"] == "L1"
    assert records[0]["smiles"] == "CCO"
    assert records[0]["score"] == "-7.2"
    assert records[0]["notes"] == "active"

    # Invariant: Empty cells must become None, never silently zero
    assert records[1]["id"] == "L2"
    assert records[1]["score"] is None
    assert records[1]["notes"] is None

    assert records[2]["id"] == "L3"
    assert records[2]["score"] == "NA"
    assert records[2]["notes"] is None


def test_read_table_records_skip_rows_comments_and_no_headers(tmp_path: Path) -> None:
    csv_file = tmp_path / "custom.csv"
    csv_file.write_text(
        "# Header note 1\n"
        "# Header note 2\n"
        "SKIP_ME\n"
        "L1,CCO,-5.2\n"
        "# inline comment\n"
        "L2,CCN,-4.1\n",
        encoding="utf-8",
    )

    schema = TableMappingSchema(
        has_header=False,
        skip_rows=3,  # Skips first 3 lines
        comment_prefix="#",
        delimiter=",",
    )

    records = list(read_table_records(csv_file, schema))
    assert len(records) == 2
    assert records[0]["col_1"] == "L1"
    assert records[0]["col_2"] == "CCO"
    assert records[0]["col_3"] == "-5.2"
    assert records[1]["col_1"] == "L2"


def test_read_and_preview_legacy_xls_through_xlrd_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeSheet:
        name = "Scores"
        nrows = 3

        @staticmethod
        def row_values(index: int) -> list[object]:
            return [
                ["id", "score"],
                ["L1", -7.2],
                ["L2", None],
            ][index]

    class FakeWorkbook:
        sheet_names = ["Scores"]

        @staticmethod
        def sheet_by_name(name: str) -> FakeSheet:
            assert name == "Scores"
            return FakeSheet()

        @staticmethod
        def sheet_by_index(index: int) -> FakeSheet:
            assert index == 0
            return FakeSheet()

        @staticmethod
        def release_resources() -> None:
            return None

    fake_xlrd = SimpleNamespace(
        open_workbook=lambda filename, on_demand: FakeWorkbook(),
    )
    monkeypatch.setitem(sys.modules, "xlrd", fake_xlrd)

    xls_file = tmp_path / "legacy.xls"
    xls_file.write_bytes(b"BIFF fixture boundary")
    schema = TableMappingSchema(sheet_name="Scores")

    records = list(read_table_records(xls_file, schema))
    assert records == [
        {"id": "L1", "score": -7.2},
        {"id": "L2", "score": None},
    ]
    headers, rows = preview_table(xls_file, sheet_name="Scores")
    assert headers == ("id", "score")
    assert rows == (("L1", -7.2), ("L2", None))


def test_read_table_records_json_and_jsonl(tmp_path: Path) -> None:
    # JSON array
    json_file = tmp_path / "stream.json"
    json_file.write_text(
        json.dumps([{"id": "A1", "val": "  ok  "}, {"id": "A2", "val": ""}]),
        encoding="utf-8",
    )
    schema = TableMappingSchema()
    records_j = list(read_table_records(json_file, schema))
    assert len(records_j) == 2
    assert records_j[0]["id"] == "A1"
    assert records_j[0]["val"] == "ok"
    assert records_j[1]["val"] is None

    # JSONL
    jsonl_file = tmp_path / "stream.jsonl"
    jsonl_file.write_text(
        '# A comment\n{"id": "B1", "score": -1.0}\n{"id": "B2", "score": null}\n',
        encoding="utf-8",
    )
    schema_jl = TableMappingSchema(comment_prefix="#")
    records_jl = list(read_table_records(jsonl_file, schema_jl))
    assert len(records_jl) == 2
    assert records_jl[0]["id"] == "B1"
    assert records_jl[0]["score"] == -1.0
    assert records_jl[1]["score"] is None


def test_preview_table_edge_cases(tmp_path: Path) -> None:
    # Empty CSV
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("", encoding="utf-8")
    assert preview_table(empty_csv) == ((), ())

    # Unknown file format
    txt_file = tmp_path / "random.bin"
    txt_file.write_bytes(b"\x00\x01\x02")
    assert preview_table(txt_file) == ((), ())
    assert detect_format(txt_file) == "unknown"
