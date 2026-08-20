from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.exc import OperationalError

from fidelichem.storage.engine import create_sqlite_engine


def _foreign_keys(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.scalar(text("PRAGMA foreign_keys")))


def test_new_and_reopened_connections_enable_foreign_keys(
    database_path: Path,
) -> None:
    engine = create_sqlite_engine(database_path)
    assert database_path.is_absolute()
    assert _foreign_keys(engine) == 1
    engine.dispose()

    reopened = create_sqlite_engine(database_path)
    assert _foreign_keys(reopened) == 1
    reopened.dispose()


def test_engine_resolves_relative_path_without_current_directory_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    relative = Path("nested") / "project.sqlite"
    engine = create_sqlite_engine(relative)

    assert Path(engine.url.database or "").is_absolute()
    engine.dispose()


def test_read_only_engine_rejects_writes(database_path: Path) -> None:
    database_path.touch()
    engine = create_sqlite_engine(database_path, read_only=True)
    with pytest.raises(OperationalError), engine.begin() as connection:
        connection.execute(text("CREATE TABLE should_fail (id INTEGER)"))
    engine.dispose()


def test_read_only_uri_supports_absolute_paths_with_spaces(tmp_path: Path) -> None:
    path = tmp_path / "space dir" / "project file.sqlite"
    path.parent.mkdir()
    path.touch()
    engine = create_sqlite_engine(path, read_only=True)
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA user_version")) == 0
    engine.dispose()


def test_read_only_engine_does_not_create_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite"
    engine = create_sqlite_engine(path, read_only=True)
    with pytest.raises((OperationalError, sqlite3.OperationalError)), engine.connect():
        pass
    assert not path.exists()
    engine.dispose()


def test_sqlalchemy_engine_is_not_used_for_in_memory_storage(
    database_path: Path,
) -> None:
    engine = create_sqlite_engine(database_path)
    assert engine.url.database != ":memory:"
    engine.dispose()


def test_direct_sqlalchemy_connections_are_not_part_of_fidelichem_contract(
    database_path: Path,
) -> None:
    engine = sqlalchemy_create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 0
    engine.dispose()
