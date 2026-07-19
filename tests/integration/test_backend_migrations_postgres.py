"""Focused PostgreSQL gate for Backend-owned Alembic revisions."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "services" / "backend" / "alembic.ini"
DATABASE_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.integration


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    if DATABASE_URL is None:
        pytest.skip("TEST_POSTGRES_URL is not configured")
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    env["PYTHONPATH"] = str(ROOT / "services" / "backend")
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _bootstrap() -> None:
    _run("-m", "migrations.bootstrap")


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return _run("-m", "alembic", "-c", str(ALEMBIC_INI), *args)


def _sql(*statements: str, fetch: str | None = None):
    if DATABASE_URL is None:
        pytest.skip("TEST_POSTGRES_URL is not configured")

    async def execute():
        engine = create_async_engine(DATABASE_URL)
        try:
            async with engine.begin() as connection:
                result = None
                for statement in statements:
                    result = await connection.execute(text(statement))
                if fetch == "all":
                    return result.fetchall()
                if fetch == "one":
                    return result.fetchone()
                return None
        finally:
            await engine.dispose()

    return asyncio.run(execute())


def _public_fingerprint():
    return _sql(
        """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """,
        fetch="all",
    )


def _events_fingerprint():
    columns = _sql(
        """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'events'
        ORDER BY table_name, ordinal_position
        """,
        fetch="all",
    )
    rows = _sql("SELECT id, payload FROM events.migration_sentinel ORDER BY id", fetch="all")
    return columns, rows


def test_postgres_fresh_partial_and_events_schema_isolation():
    _sql(
        "DROP SCHEMA IF EXISTS public CASCADE",
        "CREATE SCHEMA public",
        "DROP SCHEMA IF EXISTS events CASCADE",
        "CREATE SCHEMA events",
        "CREATE TABLE events.migration_sentinel (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)",
        "INSERT INTO events.migration_sentinel VALUES (1, 'unchanged')",
    )
    events_before = _events_fingerprint()

    _bootstrap()
    current = _alembic("current")
    assert "0003_canonical_biometric_store (head)" in current.stdout
    fresh_fingerprint = _public_fingerprint()
    _bootstrap()
    assert _public_fingerprint() == fresh_fingerprint
    assert _events_fingerprint() == events_before

    _sql("DROP SCHEMA public CASCADE", "CREATE SCHEMA public")
    _alembic("upgrade", "0001_backend_baseline")
    _sql(
        "INSERT INTO tasks (title) VALUES ('sentinel-partial')",
        "ALTER TABLE voice_events ADD COLUMN motion_id VARCHAR",
        "ALTER TABLE tasks ADD COLUMN cognitive_load INTEGER",
        "DROP TABLE bridge_status_log",
        "DROP TABLE alembic_version",
    )

    _bootstrap()

    assert _sql("SELECT title FROM tasks", fetch="all") == [("sentinel-partial",)]
    assert _sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'", fetch="one") == (33,)
    assert _events_fingerprint() == events_before
