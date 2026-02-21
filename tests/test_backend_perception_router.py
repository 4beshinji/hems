"""
Tests for backend perception router — in-memory store.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the perception router."""
    import sys
    from pathlib import Path
    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from fastapi import FastAPI
    from routers.perception import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestPerceptionGetStatus:
    def test_returns_no_data_initially(self, client):
        resp = client.get("/perception/")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "no_data"

    def test_returns_data_after_snapshot(self, client):
        snapshot = {
            "zones": {
                "living_room": {
                    "person_count": 1,
                    "activity_level": 0.45,
                    "activity_class": "low",
                    "posture_status": "sitting",
                    "posture_duration_sec": 1234,
                    "last_update": 1740100000.0,
                }
            }
        }
        resp = client.post("/perception/snapshot", json=snapshot)
        assert resp.status_code == 200
        assert resp.json() == {"updated": True}

        resp = client.get("/perception/")
        assert resp.status_code == 200
        data = resp.json()
        assert "zones" in data
        assert data["zones"]["living_room"]["person_count"] == 1
        assert data["zones"]["living_room"]["posture_status"] == "sitting"


class TestPerceptionSnapshot:
    def test_overwrites_previous_data(self, client):
        client.post("/perception/snapshot", json={"zones": {"a": {"person_count": 1}}})
        client.post("/perception/snapshot", json={"zones": {"b": {"person_count": 2}}})

        resp = client.get("/perception/")
        data = resp.json()
        assert "b" in data["zones"]
        assert "a" not in data["zones"]

    def test_empty_snapshot(self, client):
        client.post("/perception/snapshot", json={})
        resp = client.get("/perception/")
        data = resp.json()
        assert data.get("status") == "no_data"
