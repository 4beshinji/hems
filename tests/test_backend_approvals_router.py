"""Tests for backend approvals (HITL) router (Phase 0)."""

import pytest

try:
    import sqlalchemy  # noqa: F401

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

pytestmark = pytest.mark.skipif(not HAS_SQLALCHEMY, reason="sqlalchemy not installed")


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient with approvals router mounted on a tmp SQLite file."""
    import asyncio
    import sys
    from pathlib import Path

    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'hems.db'}")
    for name in ("database", "models", "auth", "approval_queue", "routers", "routers.approvals"):
        sys.modules.pop(name, None)

    from fastapi import FastAPI

    import database
    from routers import approvals

    app = FastAPI()
    app.include_router(approvals.router)

    async def _create():
        async with database.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)
        await database.engine.dispose()

    asyncio.run(_create())

    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
    asyncio.run(database.engine.dispose())


def test_create_approval(client):
    resp = client.post(
        "/approvals/",
        json={
            "action_type": "device_control",
            "risk_tier": "high",
            "reversibility": "compensatable",
            "proposed_payload": {"device_id": "zigbee.lock", "action": "lock"},
            "context": {"zone": "entrance"},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["risk_tier"] == "high"
    assert body["action_type"] == "device_control"
    approval_id = body["id"]

    # GET by id
    get = client.get(f"/approvals/{approval_id}")
    assert get.status_code == 200
    assert get.json()["id"] == approval_id


def test_list_approvals_with_status_filter(client):
    resp = client.post(
        "/approvals/",
        json={
            "action_type": "scene",
            "risk_tier": "low",
            "reversibility": "reversible",
            "proposed_payload": {"scene": "wake_up"},
        },
    )
    assert resp.status_code == 201, resp.text
    resp = client.get("/approvals/?status=pending")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.get("/approvals/?status=approved")
    assert resp.status_code == 200
    assert len(resp.json()) == 0


def test_decide_approve(client):
    create = client.post(
        "/approvals/",
        json={
            "action_type": "device_control",
            "risk_tier": "high",
            "reversibility": "compensatable",
            "proposed_payload": {"device_id": "zigbee.lock", "action": "lock"},
        },
    )
    approval_id = create.json()["id"]

    resp = client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approve", "reason": "looks good", "reviewer_id": "user-1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["decision"] == "approve"
    assert body["reviewer_id"] == "user-1"


def test_decide_modify(client):
    create = client.post(
        "/approvals/",
        json={
            "action_type": "device_control",
            "risk_tier": "medium",
            "reversibility": "reversible",
            "proposed_payload": {"device_id": "zigbee.bulb", "action": "on"},
        },
    )
    assert create.status_code == 201, create.text
    approval_id = create.json()["id"]

    modified_actions = [{"device_id": "zigbee.bulb", "action": "on", "params": {"brightness": 50}}]
    resp = client.post(
        f"/approvals/{approval_id}/decide",
        json={
            "decision": "modify",
            "modified_payload": {"actions": modified_actions},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "modified"
    assert body["proposed_payload"]["actions"] == modified_actions


def test_decide_reject_then_rollback(client):
    create = client.post(
        "/approvals/",
        json={
            "action_type": "device_control",
            "risk_tier": "high",
            "reversibility": "compensatable",
            "proposed_payload": {"device_id": "zigbee.lock", "action": "lock"},
        },
    )
    assert create.status_code == 201, create.text
    approval_id = create.json()["id"]

    resp = client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "reject", "reason": "do not lock now"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    # Rollback log
    resp = client.post(
        f"/approvals/{approval_id}/rollback",
        params={"trigger": "human_reject", "status": "success"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["trigger"] == "human_reject"
    assert body["execution_status"] == "success"

    # Approval is now rolled_back
    get = client.get(f"/approvals/{approval_id}")
    assert get.json()["status"] == "rolled_back"


def test_mark_executed(client):
    create = client.post(
        "/approvals/",
        json={
            "action_type": "scene",
            "risk_tier": "low",
            "reversibility": "reversible",
            "proposed_payload": {"scene": "wake_up"},
        },
    )
    assert create.status_code == 201, create.text
    approval_id = create.json()["id"]

    # Cannot execute before approval
    resp = client.post(f"/approvals/{approval_id}/execute")
    assert resp.status_code == 400

    client.post(f"/approvals/{approval_id}/decide", json={"decision": "approve"})
    resp = client.post(f"/approvals/{approval_id}/execute")
    assert resp.status_code == 200
    assert resp.json()["executed_at"] is not None


def test_snapshot_round_trip(client):
    create = client.post(
        "/approvals/",
        json={
            "action_type": "device_control",
            "risk_tier": "medium",
            "reversibility": "reversible",
            "proposed_payload": {"device_id": "zigbee.bulb", "action": "on"},
        },
    )
    assert create.status_code == 201, create.text
    approval_id = create.json()["id"]

    resp = client.post(
        f"/approvals/{approval_id}/snapshots",
        json={
            "approval_id": approval_id,
            "entity_type": "device",
            "entity_id": "zigbee.bulb",
            "before_state": {"on": False},
            "after_state": {"on": True},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity_type"] == "device"
    assert body["before_state"] == {"on": False}


def test_invalid_risk_tier_rejected(client):
    resp = client.post(
        "/approvals/",
        json={
            "action_type": "device_control",
            "risk_tier": "unknown",
            "reversibility": "reversible",
            "proposed_payload": {},
        },
    )
    assert resp.status_code == 400


@pytest.mark.skip(
    reason="Fixture mounts approvals router directly without auth dependency; auth is covered by main app integration tests"
)
def test_auth_required_when_api_key_set(client):
    """Placeholder: a request without/malformed Authorization header must return 401 when BACKEND_API_KEY is set."""
