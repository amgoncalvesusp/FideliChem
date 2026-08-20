"""Programmatic Alembic migration and schema-state checks."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine


class MigrationError(RuntimeError):
    """A project database cannot be safely migrated by this application."""


def _config() -> Config:
    config = Config()
    migration_path = Path(__file__).resolve().parent / "migrations"
    config.set_main_option("script_location", str(migration_path))
    return config


def _known_revisions() -> set[str]:
    script = ScriptDirectory.from_config(_config())
    return {
        revision.revision
        for revision in script.walk_revisions()
        if revision.revision is not None
    }


def head_revision() -> str:
    """Return the one supported Alembic head revision."""

    head = ScriptDirectory.from_config(_config()).get_current_head()
    if head is None:
        raise MigrationError("storage migration has no head revision")
    return head


def current_revision(engine: Engine) -> str | None:
    """Return the database revision, or ``None`` before first migration."""

    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _assert_revision_known(revision: str | None) -> None:
    if revision is not None and revision not in _known_revisions():
        raise MigrationError(f"unknown or future storage revision: {revision}")


def upgrade_database(engine: Engine) -> None:
    """Upgrade *engine* to the packaged head using one existing connection."""

    revision = current_revision(engine)
    _assert_revision_known(revision)
    config = _config()
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        try:
            command.upgrade(config, "head")
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def assert_database_current(engine: Engine) -> None:
    """Reject a database that is not exactly at this application's head."""

    revision = current_revision(engine)
    _assert_revision_known(revision)
    expected = head_revision()
    if revision != expected:
        raise MigrationError(
            f"database revision {revision!r} is not supported head {expected!r}"
        )
