"""Alembic environment for the Backend-owned public schema."""

import asyncio
import importlib
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
database_url = config.attributes.get("database_url") or os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("sqlite:///"):
    # database.py owns an AsyncEngine; keep model import async even when a
    # migration test deliberately uses SQLAlchemy's synchronous SQLite driver.
    os.environ["DATABASE_URL"] = database_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
database = importlib.import_module("database")
importlib.import_module("models")  # registers Backend tables on Base.metadata
Base = database.Base

if database_url:
    os.environ["DATABASE_URL"] = database_url

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):
    """Keep migrations scoped to Backend public tables."""
    if type_ == "table" and name not in target_metadata.tables:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    url = make_url(config.get_main_option("sqlalchemy.url"))
    if url.get_dialect().is_async:
        asyncio.run(run_async_migrations())
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
