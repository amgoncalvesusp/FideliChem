"""Adapter layer for FideliChem multi-fidelity evidence producers."""

from .base import (
    EvidenceAdapter,
    build_import_plan,
    compute_source_artifacts,
    scan_source_files,
    verify_import_plan,
)
from .docklens import DockLensAdapter
from .fake import FakeAdapter
from .gold import GoldAdapter
from .gromacs import GromacsAdapter
from .moldynstudio import MolDynStudioAdapter
from .registry import AdapterRegistry
from .smiles2docking import Smiles2DockingAdapter
from .smiles2select import Smiles2SelectAdapter
from .table import UniversalTableAdapter

__all__ = [
    "AdapterRegistry",
    "DockLensAdapter",
    "EvidenceAdapter",
    "FakeAdapter",
    "GoldAdapter",
    "GromacsAdapter",
    "MolDynStudioAdapter",
    "Smiles2DockingAdapter",
    "Smiles2SelectAdapter",
    "UniversalTableAdapter",
    "build_import_plan",
    "compute_source_artifacts",
    "scan_source_files",
    "verify_import_plan",
]
