"""Adapter layer for FideliChem multi-fidelity evidence producers."""

from .base import (
    EvidenceAdapter,
    build_import_plan,
    compute_source_artifacts,
    scan_source_files,
)
from .fake import FakeAdapter
from .gold import GoldAdapter
from .registry import AdapterRegistry
from .table import UniversalTableAdapter

__all__ = [
    "AdapterRegistry",
    "EvidenceAdapter",
    "FakeAdapter",
    "GoldAdapter",
    "UniversalTableAdapter",
    "build_import_plan",
    "compute_source_artifacts",
    "scan_source_files",
]
