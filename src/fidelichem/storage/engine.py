"""SQLite engine construction with project-wide connection invariants."""

from __future__ import annotations

import sqlite3
from os import PathLike
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL


def _resolved_path(path: str | PathLike[str]) -> Path:
    return Path(path).expanduser().resolve()


def create_sqlite_engine(
    path: str | PathLike[str],
    read_only: bool = False,
) -> Engine:
    """Create a file-backed SQLite engine with enforced foreign keys.

    A resolved absolute path is used in both modes.  Read-only engines use
    SQLite's URI ``mode=ro`` flag, so opening them can never create a file.
    """

    resolved = _resolved_path(path)
    if read_only:
        database = f"file:{resolved.as_posix()}"
        engine = create_engine(
            URL.create(
                "sqlite",
                database=database,
                query={"mode": "ro", "uri": "true"},
            )
        )
    else:
        engine = create_engine(URL.create("sqlite", database=str(resolved)))

    @event.listens_for(engine, "connect")
    def _configure_connection(
        dbapi_connection: sqlite3.Connection,
        _: object,
    ) -> None:
        original_autocommit = getattr(dbapi_connection, "autocommit", None)
        original_isolation = dbapi_connection.isolation_level
        if original_autocommit is not None:
            dbapi_connection.autocommit = True
        else:
            dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA recursive_triggers=ON")
        finally:
            cursor.close()
            if original_autocommit is not None:
                dbapi_connection.autocommit = original_autocommit
            else:
                dbapi_connection.isolation_level = original_isolation

    return engine
