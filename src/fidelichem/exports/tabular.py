"""Tabular data exporters for CSV, JSON, Excel, and Parquet."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from itertools import chain
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

_INVALID_XML_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _column_names(data: Sequence[Mapping[str, Any]]) -> list[str]:
    """Keep first-seen column order across every evidence family."""
    return list(dict.fromkeys(key for row in data for key in row))


def _tabular_value(value: Any) -> Any:
    """Represent structured evidence as JSON in scalar table cells."""
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, ensure_ascii=True)
    return value


def _excel_value(value: Any) -> Any:
    value = _tabular_value(value)
    if not isinstance(value, str):
        return value
    # Expose invalid XML characters as visible Unicode escapes; retain the
    # raw evidence in storage and JSON exports instead of deleting characters.
    text = _INVALID_XML_TEXT.sub(lambda match: f"\\u{ord(match[0]):04x}", value)
    if len(text) > 32767:
        raise ValueError(
            "Excel text exceeds the 32767 character cell limit; export JSON instead"
        )
    return text


def export_to_csv(
    data: Sequence[Mapping[str, Any]],
    target_path: Path,
    fieldnames: Sequence[str] | None = None,
) -> Path:
    """Export a sequence of dictionary records to a CSV file."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not data:
        target_path.write_text("", encoding="utf-8")
        return target_path

    keys = list(fieldnames) if fieldnames is not None else _column_names(data)

    with open(target_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            formatted_row = {
                k: ("" if row.get(k) is None else str(_tabular_value(row.get(k))))
                for k in keys
            }
            writer.writerow(formatted_row)

    return target_path


def export_to_json(
    data: Sequence[Mapping[str, Any]],
    target_path: Path,
    indent: int = 2,
) -> Path:
    """Export records to a JSON file."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(list(data), indent=indent), encoding="utf-8")
    return target_path


def export_to_xlsx(
    data: Sequence[Mapping[str, Any]],
    target_path: Path,
    sheet_name: str = "FideliChem_Export",
) -> Path:
    """Export records to an Excel workbook with XML spreadsheet fallback."""
    try:
        import openpyxl  # type: ignore[import-untyped]

        target_path.parent.mkdir(parents=True, exist_ok=True)

        wb = openpyxl.Workbook()
        ws = wb.active
        if ws is not None:
            ws.title = sheet_name

        if not data:
            wb.save(target_path)
            return target_path

        headers = _column_names(data)
        if ws is not None:
            values: Iterable[Sequence[Any]] = chain(
                (headers,), ([row.get(h) for h in headers] for row in data)
            )
            for row_index, row_values in enumerate(values, start=1):
                for column_index, value in enumerate(row_values, start=1):
                    cell = ws.cell(row_index, column_index, _excel_value(value))
                    if isinstance(cell.value, str):
                        cell.data_type = "s"

        wb.save(target_path)
        return target_path
    except ImportError:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not data:
            target_path.write_text("", encoding="utf-8")
            return target_path

        headers = _column_names(data)
        xml_lines = [
            '<?xml version="1.0"?>',
            '<?mso-application progid="Excel.Sheet"?>',
            '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
            ' xmlns:o="urn:schemas-microsoft-com:office:office"',
            ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
            ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"',
            ' xmlns:html="http://www.w3.org/TR/REC-html40">',
            f" <Worksheet ss:Name={quoteattr(sheet_name)}>",
            "  <Table>",
            "   <Row>",
        ]
        for h in headers:
            xml_lines.append(
                '    <Cell><Data ss:Type="String">'
                f"{escape(_excel_value(h))}</Data></Cell>"
            )
        xml_lines.append("   </Row>")
        for row in data:
            xml_lines.append("   <Row>")
            for h in headers:
                val = _excel_value(row.get(h))
                val_str = "" if val is None else str(val)
                val_type = "Number" if isinstance(val, (int, float)) else "String"
                xml_lines.append(
                    f'    <Cell><Data ss:Type="{val_type}">'
                    f"{escape(val_str)}</Data></Cell>"
                )
            xml_lines.append("   </Row>")
        xml_lines.extend(
            [
                "  </Table>",
                " </Worksheet>",
                "</Workbook>",
            ]
        )
        target_path.write_text("\n".join(xml_lines), encoding="utf-8")
        return target_path


def export_to_parquet(
    data: Sequence[Mapping[str, Any]],
    target_path: Path,
) -> Path:
    """Export records to Parquet format or fallback to structured CSV."""
    try:
        import pyarrow as pa  # type: ignore[import-not-found]
        import pyarrow.parquet as pq  # type: ignore[import-not-found]

        target_path.parent.mkdir(parents=True, exist_ok=True)

        if not data:
            pq.write_table(pa.Table.from_pydict({}), target_path)
            return target_path

        pydict = {k: [row.get(k) for row in data] for k in _column_names(data)}
        table = pa.Table.from_pydict(pydict)
        pq.write_table(table, target_path)
        return target_path
    except ImportError:
        return export_to_csv(data, target_path.with_suffix(".csv"))


__all__ = [
    "export_to_csv",
    "export_to_json",
    "export_to_parquet",
    "export_to_xlsx",
]
