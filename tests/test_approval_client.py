"""Tests for brain-side approval backend client (Phase 0 HITL)."""

import pytest

from approval.client import ApprovalClient, ApprovalClientError


class _FakeResponse:
    def __init__(self, status, json_data=None, content_type="application/json"):
        self.status = status
        self._json = json_data
        self.content_type = content_type

    async def json(self):
        return self._json

    async def text(self):
        return str(self._json)


class _AsyncContextWrapper:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, responses):
        self._responses = responses
        self._calls = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self._calls.append((method, url, kwargs))
        return _AsyncContextWrapper(self._responses.pop(0))

    async def close(self):
        self.closed = True


@pytest.fixture
def client():
    return ApprovalClient(backend_url="http://test")


@pytest.mark.asyncio
async def test_create_approval(client):
    fake = _FakeSession([_FakeResponse(201, {"id": "app-1", "status": "pending"})])
    client._http_session = fake
    resp = await client.create(
        action_type="device_control",
        proposed_payload={"device_id": "zigbee.lock", "action": "lock"},
        risk_tier="high",
    )
    assert resp["id"] == "app-1"
    assert fake._calls[0][0] == "POST"
    assert fake._calls[0][1] == "http://test/approvals/"


@pytest.mark.asyncio
async def test_get_approval(client):
    fake = _FakeSession([_FakeResponse(200, {"id": "app-1", "status": "approved"})])
    client._http_session = fake
    resp = await client.get("app-1")
    assert resp["status"] == "approved"


@pytest.mark.asyncio
async def test_get_missing_returns_none(client):
    fake = _FakeSession([_FakeResponse(404, {"detail": "not found"})])
    client._http_session = fake
    resp = await client.get("missing")
    assert resp is None


@pytest.mark.asyncio
async def test_record_snapshot(client):
    fake = _FakeSession([_FakeResponse(200, {"id": 1, "entity_type": "device"})])
    client._http_session = fake
    resp = await client.record_snapshot("app-1", "device", "zigbee.bulb", {"on": False}, {"on": True})
    assert resp["entity_type"] == "device"
    call = fake._calls[0]
    assert call[0] == "POST"
    assert call[1] == "http://test/approvals/app-1/snapshots"


@pytest.mark.asyncio
async def test_mark_executed(client):
    fake = _FakeSession([_FakeResponse(200, {"id": "app-1", "executed_at": "2026-01-01T00:00:00"})])
    client._http_session = fake
    resp = await client.mark_executed("app-1")
    assert resp["executed_at"] is not None


@pytest.mark.asyncio
async def test_record_rollback(client):
    fake = _FakeSession([_FakeResponse(200, {"id": 1, "trigger": "human_reject"})])
    client._http_session = fake
    resp = await client.record_rollback("app-1", "human_reject", "success")
    assert resp["trigger"] == "human_reject"
    call = fake._calls[0]
    assert call[2]["params"]["status"] == "success"


@pytest.mark.asyncio
async def test_http_error_raises(client):
    fake = _FakeSession([_FakeResponse(500, {"detail": "boom"})])
    client._http_session = fake
    with pytest.raises(ApprovalClientError):
        await client.get("app-1")
