"""
Tests for backend PC router — in-memory store.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the backend app."""
    # Need to import with correct path setup (done in conftest.py)
    import sys
    from pathlib import Path
    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    # We need to test just the PC router in isolation to avoid DB dependencies
    from fastapi import FastAPI
    from routers.pc import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestPCRouterGetStatus:
    def test_returns_no_data_initially(self, client):
        resp = client.get("/pc/")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "no_data"

    def test_returns_data_after_snapshot(self, client):
        snapshot = {
            "cpu": {"usage_percent": 42, "core_count": 8, "temp_c": 55},
            "memory": {"used_gb": 12, "total_gb": 32, "percent": 37.5},
            "bridge_connected": True,
        }
        resp = client.post("/pc/snapshot", json=snapshot)
        assert resp.status_code == 200
        assert resp.json() == {"updated": True}

        resp = client.get("/pc/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cpu"]["usage_percent"] == 42
        assert data["bridge_connected"] is True


class TestPCRouterSnapshot:
    def test_overwrites_previous_data(self, client):
        client.post("/pc/snapshot", json={"cpu": {"usage_percent": 10}})
        client.post("/pc/snapshot", json={"cpu": {"usage_percent": 90}})

        resp = client.get("/pc/")
        data = resp.json()
        assert data["cpu"]["usage_percent"] == 90
        # First snapshot's data should be completely replaced
        assert "memory" not in data

    def test_empty_snapshot(self, client):
        client.post("/pc/snapshot", json={})
        resp = client.get("/pc/")
        data = resp.json()
        # Empty snapshot clears the store, which is falsy → returns no_data
        assert data.get("status") == "no_data"
