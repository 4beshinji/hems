"""
Tests for backend GAS router (in-memory store).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestGASRouter:

    @pytest.fixture
    def client(self):
        from routers.gas import router, _gas_store
        _gas_store.clear()
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_returns_no_data_initially(self, client):
        resp = client.get("/gas/")
        assert resp.status_code == 200
        assert resp.json().get("status") == "no_data"

    def test_snapshot_updates_store(self, client):
        payload = {
            "bridge_connected": True,
            "calendar_events": [{"id": "e1", "title": "Meeting"}],
            "gmail_inbox_unread": 5,
            "overdue_count": 1,
        }
        resp = client.post("/gas/snapshot", json=payload)
        assert resp.status_code == 200
        assert resp.json() == {"updated": True}

        resp = client.get("/gas/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["bridge_connected"] is True
        assert len(data["calendar_events"]) == 1
        assert data["gmail_inbox_unread"] == 5
        assert data["overdue_count"] == 1

    def test_snapshot_replaces_previous(self, client):
        client.post("/gas/snapshot", json={"calendar_events": [{"id": "e1"}]})
        client.post("/gas/snapshot", json={"gmail_inbox_unread": 10})

        data = client.get("/gas/").json()
        assert data.get("gmail_inbox_unread") == 10
        assert "calendar_events" not in data  # Previous data was cleared

    def test_empty_snapshot(self, client):
        resp = client.post("/gas/snapshot", json={})
        assert resp.status_code == 200
        data = client.get("/gas/").json()
        assert data["status"] == "no_data"  # Empty store is treated as no data
