"""Integration tests for Phase 1 feedback pipeline.

Exercises Backend /feedback API + Brain FeedbackCollector + event_store flush
over an in-process ASGI transport and a shared SQLite database.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

try:
    import httpx
    import sqlalchemy  # noqa: F401

    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

pytestmark = pytest.mark.skipif(not HAS_DEPS, reason="httpx/sqlalchemy not installed")


@pytest.fixture
async def backend_app(monkeypatch, tmp_path):
    """Fresh backend app + event_store over a shared temp SQLite file."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/feedback_integration.db"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("BACKEND_API_KEY", "")

    for name in list(sys.modules):
        if (
            name in ("database", "models", "schemas", "auth", "approval_queue")
            or name.startswith("routers")
            or name.startswith("event_store")
        ):
            sys.modules.pop(name, None)

    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    sys.path.insert(0, str(backend_path))
    try:
        spec = importlib.util.spec_from_file_location("backend_main", backend_path / "main.py")
        backend_main = importlib.util.module_from_spec(spec)
        sys.modules["backend_main"] = backend_main
        spec.loader.exec_module(backend_main)
    finally:
        sys.path.pop(0)

    import database as backend_database

    async with backend_database.engine.begin() as conn:
        await conn.run_sync(backend_database.Base.metadata.create_all)

    from event_store.database import init_db

    event_engine = await init_db()

    transport = httpx.ASGITransport(app=backend_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, event_engine

    await backend_database.engine.dispose()
    if event_engine is not None:
        await event_engine.dispose()


@pytest.fixture
async def feedback_collector(backend_app):
    """Brain FeedbackCollector wired to the shared event_store engine."""
    from event_store.writer import EventWriter
    from feedback import FeedbackCollector

    _, engine = backend_app
    writer = EventWriter(engine) if engine is not None else None
    if writer is not None:
        asyncio.create_task(writer.start())
    collector = FeedbackCollector(event_writer=writer)
    yield collector
    if writer is not None:
        await writer.stop()


@pytest.mark.asyncio
async def test_feedback_post_persists_in_backend(backend_app):
    client, _ = backend_app
    resp = await client.post(
        "/feedback/",
        json={
            "target_type": "task",
            "target_id": "99",
            "feedback_type": "explicit_up",
            "channel": "frontend",
            "user_id": "user-1",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["feedback_type"] == "explicit_up"

    stats = await client.get("/feedback/stats?target_type=task&target_id=99")
    assert stats.status_code == 200, stats.text
    assert stats.json()["positive"] == 1


@pytest.mark.asyncio
async def test_explicit_feedback_reaches_event_store(backend_app, feedback_collector):
    client, engine = backend_app
    resp = await client.post(
        "/feedback/",
        json={
            "target_type": "voice",
            "target_id": "5",
            "feedback_type": "explicit_down",
            "channel": "frontend",
        },
    )
    assert resp.status_code == 201
    payload = resp.json()

    # Simulate the MQTT path Brain would take on a hems/feedback/... message.
    feedback_collector.collect_explicit(
        target_type=payload["target_type"],
        target_id=payload["target_id"],
        feedback_type=payload["feedback_type"],
        channel=payload["channel"],
        payload=payload.get("payload"),
        context=payload.get("context"),
        user_id=payload.get("user_id"),
    )

    # Force event_writer flush.
    writer = feedback_collector.event_writer
    if writer is not None:
        await writer._flush()

    from sqlalchemy import text

    async with engine.begin() as conn:
        rows = await conn.execute(
            text("SELECT target_type, target_id, feedback_type FROM agent_feedback ORDER BY id DESC LIMIT 1")
        )
        row = rows.fetchone()
    assert row is not None
    assert row.target_type == "voice"
    assert row.feedback_type == "explicit_down"
