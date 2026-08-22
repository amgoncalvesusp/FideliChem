"""Tabular data exporters for CSV, JSON, Excel, and Parquet."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


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

    keys = list(fieldnames) if fieldnames is not None else list(data[0].keys())

    with open(target_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            formatted_row = {
                k: ("" if row.get(k) is None else str(row.get(k))) for k in keys
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

        headers = list(data[0].keys())
        if ws is not None:
            ws.append(headers)
            for row in data:
                ws.append([row.get(h) for h in headers])

        wb.save(target_path)
        return target_path
    except ImportError:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not data:
            target_path.write_text("", encoding="utf-8")
            return target_path

        headers = list(data[0].keys())
        xml_lines = [
            '<?xml version="1.0"?>',
            '<?mso-application progid="Excel.Sheet"?>',
            '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
            ' xmlns:o="urn:schemas-microsoft-com:office:office"',
            ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
            ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"',
            ' xmlns:html="http://www.w3.org/TR/REC-html40">',
            f' <Worksheet ss:Name="{sheet_name}">',
            "  <Table>",
            "   <Row>",
        ]
        for h in headers:
            xml_lines.append(f'    <Cell><Data ss:Type="String">{h}</Data></Cell>')
        xml_lines.append("   </Row>")
        for row in data:
            xml_lines.append("   <Row>")
            for h in headers:
                val = row.get(h)
                val_str = "" if val is None else str(val)
                val_type = "Number" if isinstance(val, (int, float)) else "String"
                xml_lines.append(
                    f'    <Cell><Data ss:Type="{val_type}">{val_str}</Data></Cell>'
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

        pydict = {k: [row.get(k) for row in data] for k in data[0]}
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
