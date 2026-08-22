"""SQLite-backed persistence primitives for FideliChem projects."""

from .chemistry_repositories import (
    AliasRepository,
    CompoundRepository,
    IdentityResolutionRepository,
    MolecularStateRepository,
)
from .engine import create_sqlite_engine
from .runner import (
    MigrationError,
    assert_database_current,
    current_revision,
    head_revision,
    upgrade_database,
)

__all__ = [
    "MigrationError",
    "AliasRepository",
    "CompoundRepository",
    "IdentityResolutionRepository",
    "MolecularStateRepository",
    "assert_database_current",
    "create_sqlite_engine",
    "current_revision",
    "head_revision",
    "upgrade_database",
]
