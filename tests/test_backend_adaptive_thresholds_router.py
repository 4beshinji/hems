"""Tests for backend adaptive thresholds router (Phase 2)."""

import pytest

try:
    import sqlalchemy  # noqa: F401

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

pytestmark = pytest.mark.skipif(not HAS_SQLALCHEMY, reason="sqlalchemy not installed")


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient with adaptive thresholds router mounted on a tmp SQLite file."""
    import asyncio
    import sys
    from pathlib import Path

    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'hems.db'}")
    for name in (
        "database",
        "models",
        "auth",
        "schemas",
        "routers",
        "routers.adaptive_thresholds",
    ):
        sys.modules.pop(name, None)

    from fastapi import FastAPI

    import database
    from routers import adaptive_thresholds

    app = FastAPI()
    app.include_router(adaptive_thresholds.router)

    async def _create():
        async with database.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)
        await database.engine.dispose()

    asyncio.run(_create())

    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
    asyncio.run(database.engine.dispose())


def test_create_proposal(client):
    resp = client.post(
        "/thresholds/proposals",
        json={
            "metric_key": "co2_high",
            "detector": "adwin",
            "old_value": 1000.0,
            "proposed_value": 1100.0,
            "reason": "drift",
            "status": "proposed",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["metric_key"] == "co2_high"
    assert body["status"] == "proposed"
    assert body["id"] is not None


def test_duplicate_open_proposal_rejected(client):
    payload = {
        "metric_key": "co2_high",
        "detector": "adwin",
        "old_value": 1000.0,
        "proposed_value": 1100.0,
    }
    r1 = client.post("/thresholds/proposals", json=payload)
    assert r1.status_code == 201
    r2 = client.post("/thresholds/proposals", json=payload)
    assert r2.status_code == 409


def test_approve_proposal_creates_adjustment(client):
    proposal = client.post(
        "/thresholds/proposals",
        json={
            "metric_key": "temp_high",
            "detector": "adwin",
            "old_value": 28.0,
            "proposed_value": 30.0,
        },
    ).json()

    resp = client.post(
        f"/thresholds/proposals/{proposal['id']}/decide",
        json={"decision": "approve", "reviewer_id": "user-1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"

    adjustments = client.get("/thresholds/adjustments").json()
    assert len(adjustments) == 1
    assert adjustments[0]["metric_key"] == "temp_high"
    assert adjustments[0]["offset"] == 2.0
    assert adjustments[0]["approved_by"] == "user"


def test_reject_proposal(client):
    proposal = client.post(
        "/thresholds/proposals",
        json={
            "metric_key": "humidity_high",
            "detector": "adwin",
            "old_value": 70.0,
            "proposed_value": 75.0,
        },
    ).json()

    resp = client.post(
        f"/thresholds/proposals/{proposal['id']}/decide",
        json={"decision": "reject"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"
    assert client.get("/thresholds/adjustments").json() == []


def test_list_proposals_filter_by_status(client):
    client.post(
        "/thresholds/proposals",
        json={"metric_key": "pm25_high", "detector": "adwin", "old_value": 35.0, "proposed_value": 40.0},
    )
    resp = client.get("/thresholds/proposals?status=proposed")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_invalid_status_rejected(client):
    resp = client.post(
        "/thresholds/proposals",
        json={
            "metric_key": "co2_high",
            "detector": "adwin",
            "status": "invalid",
        },
    )
    assert resp.status_code == 400
