from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.runner import upgrade_database


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "project.fidelichem.sqlite"


@pytest.fixture
def migrated_engine(database_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(database_path)
    upgrade_database(engine)
    try:
        yield engine
    finally:
        engine.dispose()
