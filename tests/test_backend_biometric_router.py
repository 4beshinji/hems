"""
Tests for backend biometric router — in-memory store.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the backend app."""
    import sys
    from pathlib import Path
    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    # Test just the biometric router in isolation to avoid DB dependencies
    from fastapi import FastAPI
    from routers.biometric import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestBiometricRouterGetStatus:
    def test_returns_no_data_initially(self, client):
        resp = client.get("/biometric/")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "no_data"

    def test_returns_data_after_snapshot(self, client):
        snapshot = {
            "heart_rate": {"bpm": 72, "source": "fitbit"},
            "sleep": {"hours": 7.5, "quality": "good"},
            "steps": 8432,
        }
        resp = client.post("/biometric/snapshot", json=snapshot)
        assert resp.status_code == 200
        assert resp.json() == {"updated": True}

        resp = client.get("/biometric/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["heart_rate"]["bpm"] == 72
        assert data["steps"] == 8432


class TestBiometricRouterSnapshot:
    def test_overwrites_previous_data(self, client):
        client.post("/biometric/snapshot", json={"heart_rate": {"bpm": 60}})
        client.post("/biometric/snapshot", json={"heart_rate": {"bpm": 95}})

        resp = client.get("/biometric/")
        data = resp.json()
        assert data["heart_rate"]["bpm"] == 95
        # First snapshot's data should be completely replaced
        assert "sleep" not in data

    def test_empty_snapshot(self, client):
        client.post("/biometric/snapshot", json={})
        resp = client.get("/biometric/")
        data = resp.json()
        # Empty snapshot clears the store, which is falsy -> returns no_data
        assert data.get("status") == "no_data"
