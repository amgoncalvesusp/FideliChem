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
from .smiles2docking import Smiles2DockingAdapter
from .smiles2select import Smiles2SelectAdapter
from .table import UniversalTableAdapter

__all__ = [
    "AdapterRegistry",
    "EvidenceAdapter",
    "FakeAdapter",
    "GoldAdapter",
    "Smiles2DockingAdapter",
    "Smiles2SelectAdapter",
    "UniversalTableAdapter",
    "build_import_plan",
    "compute_source_artifacts",
    "scan_source_files",
]
