"""Integration tests for the Phase 0 HITL approval flow.

These tests wire the Brain :class:`ApprovalGate` and :class:`ApprovalClient`
to the real backend approvals router via an in-process ASGI transport.  No
external services are required, but the test exercises the full round-trip:
create → poll → decide → execute (or rollback).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

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
    """Fresh backend FastAPI app served over ASGI with an isolated SQLite DB."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/approval_integration.db"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("BACKEND_API_KEY", "")

    # Force a clean import so the engine is bound to the temp database.
    for name in list(sys.modules):
        if name in ("database", "models", "schemas", "auth", "approval_queue") or name.startswith("routers"):
            sys.modules.pop(name, None)

    # Import the backend main module explicitly; brain/src also has a main.py,
    # so we load it via importlib to avoid shadowing.
    import importlib.util

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

    transport = httpx.ASGITransport(app=backend_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await backend_database.engine.dispose()


@pytest.fixture
async def approval_client(backend_app):
    """Brain ApprovalClient that routes HTTP over the in-process ASGI app."""
    from approval.client import ApprovalClient, ApprovalClientError
    from brain_constants import backend_auth_headers

    class FastAsgiApprovalClient(ApprovalClient):
        def __init__(self, http_client: httpx.AsyncClient, backend_url: str = "http://testserver"):
            self.http_client = http_client
            self.backend_url = backend_url
            self._http_session = None
            self._owned_session = False

        async def _request(
            self,
            method: str,
            path: str,
            *,
            json: dict[str, Any] | None = None,
            params: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            headers = backend_auth_headers()
            resp = await self.http_client.request(
                method,
                f"/approvals{path}",
                headers=headers,
                json=json,
                params=params,
                timeout=10,
            )
            content_type = resp.headers.get("content-type", "")
            body = resp.json() if "application/json" in content_type else resp.text
            if resp.status_code >= 400:
                raise ApprovalClientError(f"HTTP {resp.status_code}: {body}")
            return body if isinstance(body, dict) else {"raw": body}

        async def poll_decision(
            self,
            approval_id: str,
            timeout_seconds: float = 300,
            poll_interval: float = 0.05,
        ) -> dict[str, Any]:
            return await ApprovalClient.poll_decision(self, approval_id, timeout_seconds, poll_interval)

        async def close(self) -> None:
            pass

    return FastAsgiApprovalClient(backend_app)


async def _wait_for_pending(client: httpx.AsyncClient) -> str:
    """Poll the backend queue until a pending approval appears."""
    for _ in range(100):
        resp = await client.get("/approvals/?status=pending")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data:
            return data[0]["id"]
        await asyncio.sleep(0.02)
    raise AssertionError("pending approval was not created")


@pytest.mark.asyncio
async def test_approve_and_execute(backend_app, approval_client):
    """High-risk rule is gated, approved, and then executed."""
    executed: list[dict[str, Any]] = []

    async def executor(actions: list[dict[str, Any]]) -> dict[str, Any]:
        executed.extend(actions)
        return {"success": True, "executed": len(actions)}

    states = {"zigbee.lock": {"on": True}}

    async def state_lookup(device_id: str) -> dict[str, Any] | None:
        return {"device_id": device_id, "last_state": states.get(device_id, {})}

    from approval.gate import ApprovalGate

    gate = ApprovalGate(
        client=approval_client,
        executor=executor,
        state_lookup=state_lookup,
    )

    rule = {
        "id": 1,
        "name": "lock entrance",
        "trigger_type": "manual",
        "risk_tier": "high",
        "reversibility": "compensatable",
        "approval_required": True,
        "actions": [{"device_id": "zigbee.lock", "action": "lock"}],
    }

    task = asyncio.create_task(gate.execute_rule(rule))
    approval_id = await _wait_for_pending(backend_app)

    resp = await backend_app.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approve", "reason": "user is leaving", "reviewer_id": "user-1"},
    )
    assert resp.status_code == 200, resp.text

    result = await asyncio.wait_for(task, timeout=5)
    assert result["success"] is True
    assert result["approval_status"] == "approved"
    assert result["approval_id"] == approval_id
    assert executed == [{"device_id": "zigbee.lock", "action": "lock"}]

    resp = await backend_app.get(f"/approvals/{approval_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["executed_at"] is not None
    assert body["decision"] == "approve"
    assert body["reviewer_id"] == "user-1"


@pytest.mark.asyncio
async def test_modify_and_execute_modified_payload(backend_app, approval_client):
    """Approver modifies the action payload; gate executes the modified version."""
    executed: list[dict[str, Any]] = []

    async def executor(actions: list[dict[str, Any]]) -> dict[str, Any]:
        executed.extend(actions)
        return {"success": True, "executed": len(actions)}

    from approval.gate import ApprovalGate

    gate = ApprovalGate(client=approval_client, executor=executor)

    rule = {
        "id": 2,
        "name": "dim lights",
        "trigger_type": "schedule",
        "risk_tier": "medium",
        "reversibility": "reversible",
        "approval_required": True,
        "actions": [{"device_id": "zigbee.bulb", "action": "on"}],
    }

    task = asyncio.create_task(gate.execute_rule(rule))
    approval_id = await _wait_for_pending(backend_app)

    modified_actions = [{"device_id": "zigbee.bulb", "action": "on", "params": {"brightness": 50}}]
    resp = await backend_app.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "modify", "modified_payload": {"actions": modified_actions}},
    )
    assert resp.status_code == 200, resp.text

    result = await asyncio.wait_for(task, timeout=5)
    assert result["success"] is True
    assert result["approval_status"] == "modified"
    assert executed == modified_actions

    resp = await backend_app.get(f"/approvals/{approval_id}")
    assert resp.json()["status"] == "modified"
    assert resp.json()["proposed_payload"]["actions"] == modified_actions


@pytest.mark.asyncio
async def test_reject_does_not_execute_rollback(backend_app, approval_client):
    """Rejected approval cancels execution and does not perform rollback."""
    executed: list[dict[str, Any]] = []

    async def executor(actions: list[dict[str, Any]]) -> dict[str, Any]:
        executed.extend(actions)
        return {"success": True, "executed": len(actions)}

    states = {"zigbee.lock": {"on": True}}

    async def state_lookup(device_id: str) -> dict[str, Any] | None:
        return {"device_id": device_id, "last_state": states.get(device_id, {})}

    from approval.gate import ApprovalGate

    gate = ApprovalGate(
        client=approval_client,
        executor=executor,
        state_lookup=state_lookup,
    )

    rule = {
        "id": 3,
        "name": "lock entrance",
        "trigger_type": "manual",
        "risk_tier": "high",
        "reversibility": "compensatable",
        "approval_required": True,
        "actions": [{"device_id": "zigbee.lock", "action": "lock"}],
    }

    task = asyncio.create_task(gate.execute_rule(rule))
    approval_id = await _wait_for_pending(backend_app)

    resp = await backend_app.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "reject", "reason": "do not lock now"},
    )
    assert resp.status_code == 200, resp.text

    result = await asyncio.wait_for(task, timeout=5)
    assert result["success"] is False
    assert result["approval_status"] == "rejected"
    assert "rollback" not in result or result.get("rollback") is None
    assert executed == []

    resp = await backend_app.get(f"/approvals/{approval_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "rejected"
