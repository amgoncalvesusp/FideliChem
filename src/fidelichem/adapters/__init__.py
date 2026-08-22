"""Adapter layer for FideliChem multi-fidelity evidence producers."""

from .base import (
    EvidenceAdapter,
    build_import_plan,
    compute_source_artifacts,
    scan_source_files,
)
from .fake import FakeAdapter
from .registry import AdapterRegistry

__all__ = [
    "AdapterRegistry",
    "EvidenceAdapter",
    "FakeAdapter",
    "build_import_plan",
    "compute_source_artifacts",
    "scan_source_files",
]
