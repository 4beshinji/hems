"""PostgreSQL runtime gate for the Brain event store."""

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_postgres_event_store_initializes_and_flushes_native_timestamps(monkeypatch):
    if DATABASE_URL is None:
        pytest.skip("TEST_POSTGRES_URL is not configured")

    cleanup_engine = create_async_engine(DATABASE_URL)
    async with cleanup_engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA IF EXISTS events CASCADE"))
    await cleanup_engine.dispose()

    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    for name in list(sys.modules):
        if name == "event_store" or name.startswith("event_store."):
            sys.modules.pop(name, None)
    monkeypatch.syspath_prepend(str(ROOT / "services" / "brain" / "src"))

    from event_store import EventWriter, init_db

    engine = await init_db()
    assert engine is not None
    writer = EventWriter(engine)
    writer.record_sensor("e2e", "co2", 1800, device_id="env-e2e")
    writer.record_world_event("e2e", "hems/e2e", {"value": 1})
    writer.record_decision(cycle_duration=0.1, iterations=1, total_tool_calls=1)
    writer.record_feedback("task", "e2e", "explicit_up")
    writer.record_trajectory("cycle-e2e", "decision-e2e", [], [], {}, {})
    writer.record_drift_detection("co2_high", "e2e", 1000, 1100)

    await writer._flush()

    async with engine.begin() as connection:
        counts = {}
        for table in (
            "raw_events",
            "world_events",
            "llm_decisions",
            "agent_feedback",
            "agent_trajectories",
            "drift_detections",
        ):
            counts[table] = (await connection.execute(text(f"SELECT count(*) FROM events.{table}"))).scalar_one()
    assert counts == {table: 1 for table in counts}
    await engine.dispose()
