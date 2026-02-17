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
    from routers.services import router

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
