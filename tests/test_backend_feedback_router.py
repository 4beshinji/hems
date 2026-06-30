"""Tests for backend feedback router (Phase 1)."""

import pytest

try:
    import sqlalchemy  # noqa: F401

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

pytestmark = pytest.mark.skipif(not HAS_SQLALCHEMY, reason="sqlalchemy not installed")


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient with feedback router mounted on a tmp SQLite file."""
    import asyncio
    import sys
    from pathlib import Path

    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'hems.db'}")
    for name in ("database", "models", "auth", "schemas", "routers", "routers.feedback"):
        sys.modules.pop(name, None)

    from fastapi import FastAPI

    import database
    from routers import feedback

    app = FastAPI()
    app.include_router(feedback.router)

    async def _create():
        async with database.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)

    asyncio.new_event_loop().run_until_complete(_create())

    from fastapi.testclient import TestClient

    return TestClient(app)


def test_create_feedback(client):
    resp = client.post(
        "/feedback/",
        json={
            "target_type": "task",
            "target_id": "42",
            "feedback_type": "explicit_up",
            "channel": "frontend",
            "payload": {"note": "helpful"},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["target_type"] == "task"
    assert body["feedback_type"] == "explicit_up"
    assert body["channel"] == "frontend"
    assert body["id"] is not None


def test_invalid_target_type_rejected(client):
    resp = client.post(
        "/feedback/",
        json={
            "target_type": "unknown",
            "target_id": "1",
            "feedback_type": "explicit_up",
        },
    )
    assert resp.status_code == 400


def test_list_feedback_with_filters(client):
    client.post(
        "/feedback/",
        json={
            "target_type": "voice",
            "target_id": "5",
            "feedback_type": "explicit_down",
        },
    )
    resp = client.get("/feedback/?target_type=voice&feedback_type=explicit_down")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["target_id"] == "5"


def test_feedback_stats(client):
    client.post("/feedback/", json={"target_type": "task", "target_id": "1", "feedback_type": "explicit_up"})
    client.post("/feedback/", json={"target_type": "task", "target_id": "1", "feedback_type": "explicit_up"})
    client.post("/feedback/", json={"target_type": "task", "target_id": "1", "feedback_type": "explicit_down"})
    client.post("/feedback/", json={"target_type": "task", "target_id": "1", "feedback_type": "cancel"})

    resp = client.get("/feedback/stats?target_type=task&target_id=1")
    assert resp.status_code == 200, resp.text
    stats = resp.json()
    assert stats["total"] == 4
    assert stats["positive"] == 2
    assert stats["negative"] == 1
    assert stats["cancels"] == 1


def test_create_trajectory(client):
    resp = client.post(
        "/feedback/trajectory",
        json={
            "cycle_id": "cycle-1",
            "decision_id": "dec-1",
            "tool_calls": [{"tool": "set_light", "success": True}],
            "outcome_summary": {"feedback_type": "explicit_up"},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["cycle_id"] == "cycle-1"


def test_list_trajectories(client):
    client.post("/feedback/trajectory", json={"cycle_id": "cycle-1", "outcome_summary": {}})
    resp = client.get("/feedback/trajectory?cycle_id=cycle-1")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
