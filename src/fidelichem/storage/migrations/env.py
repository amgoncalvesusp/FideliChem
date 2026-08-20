"""Alembic environment used by the programmatic migration runner."""

from __future__ import annotations

from logging.config import fileConfig
from typing import cast

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool

from fidelichem.storage.orm import Base

config = context.config  # pragma: no cover
if config.config_file_name is not None:  # pragma: no cover
    fileConfig(config.config_file_name)

target_metadata = Base.metadata  # pragma: no cover


def run_migrations_offline() -> None:  # pragma: no cover
    """Run migrations without a live connection for Alembic tooling."""

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:  # pragma: no cover
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:  # pragma: no cover
    """Run against the runner's existing connection when supplied."""

    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        _run_migrations(cast(Connection, supplied_connection))
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():  # pragma: no cover
    run_migrations_offline()
else:
    run_migrations_online()
