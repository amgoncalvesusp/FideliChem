"""Robust tabular file inspection, format detection, and streaming record extraction."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fidelichem.domain.table_importer import TableMappingSchema


def detect_format(file_path: Path) -> str:
    """Identify the tabular file format based on extension and content."""
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".tsv":
        return "tsv"
    if suffix == ".json":
        return "json"
    if suffix in (".jsonl", ".ndjson"):
        return "jsonl"
    if suffix == ".parquet":
        return "parquet"
    if suffix in (".xlsx", ".xlsm"):
        return "xlsx"
    if suffix == ".xls":
        return "xls"

    # Fallback to content inspection if extension is generic
    try:
        sample = file_path.read_text(encoding="utf-8", errors="ignore")[:4096].strip()
        if sample.startswith("[") and sample.endswith("]"):
            return "json"
        if sample.startswith("{"):
            return "jsonl"
    except Exception:
        pass

    return "unknown"


def detect_delimiter(file_path: Path) -> str:
    """Inspect CSV/TSV header and content to deduce the field delimiter."""
    suffix = file_path.suffix.lower()
    if suffix == ".tsv":
        return "\t"

    try:
        sample = file_path.read_text(encoding="utf-8", errors="ignore")[:8192]
        lines = [
            line.strip()
            for line in sample.splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if not lines:
            return ","

        first_line = lines[0]
        # Count candidate delimiter frequencies in first line
        delimiters = [",", "\t", ";", "|"]
        counts = {d: first_line.count(d) for d in delimiters}
        best_delimiter = max(counts, key=counts.get)  # type: ignore[arg-type]
        if counts[best_delimiter] > 0:
            return best_delimiter

        # Try csv.Sniffer fallback
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff("\n".join(lines[:5]), delimiters=",\t;|")
        return dialect.delimiter
    except Exception:
        return ","


def preview_table(
    file_path: Path,
    max_rows: int = 10,
    *,
    delimiter: str | None = None,
    sheet_name: str | None = None,
) -> tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]]:
    """Return headers and preview rows for UI and mapping setup."""
    fmt = detect_format(file_path)

    if fmt in ("csv", "tsv"):
        delim = delimiter or detect_delimiter(file_path)
        with file_path.open(
            mode="r", encoding="utf-8", errors="replace", newline=""
        ) as f:
            reader = csv.reader(f, delimiter=delim)
            rows: list[list[str]] = []
            for row in reader:
                if not row or (row and row[0].startswith("#")):
                    continue
                rows.append([cell.strip() for cell in row])
                if len(rows) > max_rows:
                    break

            if not rows:
                return ((), ())

            headers = tuple(rows[0])
            csv_data_rows: tuple[tuple[Any, ...], ...] = tuple(
                tuple(r) for r in rows[1 : max_rows + 1]
            )
            return (headers, csv_data_rows)

    if fmt == "json":
        with file_path.open(mode="r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                headers = tuple(sorted(data[0].keys()))
                json_data_rows: list[tuple[Any, ...]] = []
                for item in data[:max_rows]:
                    if isinstance(item, dict):
                        json_data_rows.append(tuple(item.get(h) for h in headers))
                return (headers, tuple(json_data_rows))
            return ((), ())

    if fmt == "jsonl":
        with file_path.open(mode="r", encoding="utf-8", errors="replace") as f:
            records: list[dict[str, Any]] = []
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    try:
                        obj = json.loads(stripped)
                        if isinstance(obj, dict):
                            records.append(obj)
                            if len(records) >= max_rows + 1:
                                break
                    except json.JSONDecodeError:
                        continue

            if not records:
                return ((), ())

            all_keys: set[str] = set()
            for r in records:
                all_keys.update(r.keys())
            headers = tuple(sorted(all_keys))

            jsonl_data_rows: tuple[tuple[Any, ...], ...] = tuple(
                tuple(r.get(h) for h in headers) for r in records[:max_rows]
            )
            return (headers, jsonl_data_rows)

    return ((), ())


def _clean_cell(val: Any) -> Any:
    """Normalize cell values: empty strings and whitespace become None."""
    if val is None:
        return None
    if isinstance(val, str):
        cleaned = val.strip()
        return cleaned if cleaned else None
    return val


def read_table_records(
    file_path: Path,
    schema: TableMappingSchema,
) -> Iterator[dict[str, Any]]:
    """Stream tabular rows as normalized dictionaries of column -> value."""
    fmt = detect_format(file_path)

    if fmt in ("csv", "tsv"):
        delim = schema.delimiter or detect_delimiter(file_path)
        with file_path.open(
            mode="r", encoding="utf-8", errors="replace", newline=""
        ) as f:
            # Skip initial rows if requested
            for _ in range(schema.skip_rows):
                f.readline()

            reader = csv.reader(f, delimiter=delim)
            headers: list[str] = []

            for row in reader:
                if not row:
                    continue
                if schema.comment_prefix and row[0].startswith(schema.comment_prefix):
                    continue

                if not headers:
                    if schema.has_header:
                        headers = [cell.strip() for cell in row]
                        continue
                    headers = [f"col_{i + 1}" for i in range(len(row))]

                record: dict[str, Any] = {}
                for idx, col_name in enumerate(headers):
                    raw_val = row[idx] if idx < len(row) else None
                    record[col_name] = _clean_cell(raw_val)

                yield record

    elif fmt == "json":
        with file_path.open(mode="r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        yield {k: _clean_cell(v) for k, v in item.items()}

    elif fmt == "jsonl":
        with file_path.open(mode="r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if stripped and (
                    not schema.comment_prefix
                    or not stripped.startswith(schema.comment_prefix)
                ):
                    try:
                        obj = json.loads(stripped)
                        if isinstance(obj, dict):
                            yield {k: _clean_cell(v) for k, v in obj.items()}
                    except json.JSONDecodeError:
                        continue


__all__ = [
    "detect_delimiter",
    "detect_format",
    "preview_table",
    "read_table_records",
]
