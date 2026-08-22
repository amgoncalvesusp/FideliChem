"""Universal table importer for heterogeneous tabular files and mappings."""

from .adapter import UniversalTableAdapter
from .presets import PresetManager
from .readers import (
    detect_delimiter,
    detect_format,
    preview_table,
    read_table_records,
)

__all__ = [
    "PresetManager",
    "UniversalTableAdapter",
    "detect_delimiter",
    "detect_format",
    "preview_table",
    "read_table_records",
]
