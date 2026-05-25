"""Regression test for event-store init against a pre-cause_event_id schema.

Reproduces the bug where init_db aborted with "no such column: cause_event_id"
on databases created before that column existed, because the DDL built the
index on cause_event_id before the migration added the column.
"""

import sqlite3

import pytest


@pytest.mark.asyncio
async def test_init_db_migrates_pre_cause_event_id_schema(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    # Simulate a pre-cause_event_id / pre-token-columns deployment.
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE llm_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            cycle_duration_sec REAL,
            iterations INTEGER,
            total_tool_calls INTEGER,
            trigger_events TEXT DEFAULT '[]',
            tool_calls TEXT DEFAULT '[]',
            world_state_snapshot TEXT DEFAULT '{}'
        )"""
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    from event_store import init_db

    # Pre-fix this raised sqlite3.OperationalError: no such column: cause_event_id
    engine = await init_db()
    assert engine is not None

    from sqlalchemy import text

    async with engine.begin() as c:
        cols = [r[1] for r in await c.execute(text("PRAGMA table_info(llm_decisions)"))]
        idx = [r[0] for r in await c.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))]
    # Migration backfilled the column, the metering columns, and the index.
    assert "cause_event_id" in cols
    assert "prompt_tokens" in cols
    assert "completion_tokens" in cols
    assert "idx_llm_decisions_cause" in idx
    # The new efficacy table is created too.
    async with engine.begin() as c:
        tables = [r[0] for r in await c.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))]
    assert "intervention_efficacy" in tables
    await engine.dispose()
