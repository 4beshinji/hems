"""
Tests for backend services router — in-memory store.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the services router."""
    import sys
    from pathlib import Path
    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from fastapi import FastAPI
    from routers.services import router, _services_store

    # Clear store before each test to ensure isolation
    _services_store.clear()

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestServicesRouterGetStatus:
    def test_returns_no_data_initially(self, client):
        resp = client.get("/services/")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "no_data"

    def test_returns_data_after_snapshot(self, client):
        snapshot = {
            "gmail": {
                "name": "gmail", "available": True, "unread_count": 3,
                "summary": "未読メール: 3通", "last_check": 1000000,
                "error": None,
            },
            "github": {
                "name": "github", "available": True, "unread_count": 5,
                "summary": "GitHub通知: 5件", "last_check": 1000000,
                "error": None,
            },
        }
        resp = client.post("/services/snapshot", json=snapshot)
        assert resp.status_code == 200
        assert resp.json() == {"updated": True}

        resp = client.get("/services/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["gmail"]["unread_count"] == 3
        assert data["github"]["unread_count"] == 5

    def test_returns_all_fields(self, client):
        snapshot = {
            "gmail": {
                "name": "gmail", "available": False, "unread_count": 0,
                "summary": "Gmail接続エラー", "error": "IMAP timeout",
                "last_check": 1000000,
            },
        }
        client.post("/services/snapshot", json=snapshot)
        resp = client.get("/services/")
        data = resp.json()
        assert data["gmail"]["available"] is False
        assert data["gmail"]["error"] == "IMAP timeout"


class TestServicesRouterSnapshot:
    def test_overwrites_previous_data(self, client):
        client.post("/services/snapshot", json={
            "gmail": {"name": "gmail", "unread_count": 10},
        })
        client.post("/services/snapshot", json={
            "gmail": {"name": "gmail", "unread_count": 2},
        })

        resp = client.get("/services/")
        data = resp.json()
        assert data["gmail"]["unread_count"] == 2
        assert "github" not in data

    def test_empty_snapshot(self, client):
        client.post("/services/snapshot", json={})
        resp = client.get("/services/")
        data = resp.json()
        assert data.get("status") == "no_data"

    def test_snapshot_replaces_all_keys(self, client):
        """Second snapshot completely replaces first — no stale keys."""
        client.post("/services/snapshot", json={
            "gmail": {"name": "gmail", "unread_count": 3},
            "github": {"name": "github", "unread_count": 1},
        })
        client.post("/services/snapshot", json={
            "line": {"name": "line", "unread_count": 5},
        })
        resp = client.get("/services/")
        data = resp.json()
        assert "line" in data
        assert "gmail" not in data
        assert "github" not in data

    def test_snapshot_returns_updated_true(self, client):
        resp = client.post("/services/snapshot", json={"gmail": {"unread_count": 1}})
        assert resp.status_code == 200
        assert resp.json() == {"updated": True}
