"""SQLite-backed persistence primitives for FideliChem projects."""

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
    "assert_database_current",
    "create_sqlite_engine",
    "current_revision",
    "head_revision",
    "upgrade_database",
]
