"""
Tests for backend home (HA control) router — in-memory store + httpx proxy.
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the home router."""
    import sys
    from pathlib import Path
    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from fastapi import FastAPI
    from routers.home import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestHomeGetStatus:
    def test_returns_no_data_initially(self, client):
        resp = client.get("/home/")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "no_data"

    def test_returns_data_after_snapshot(self, client):
        snapshot = {
            "bridge_connected": True,
            "lights": {"light.living_room": {"on": True, "brightness": 200}},
            "climates": {"climate.living_room": {"mode": "cool", "target_temp": 26, "current_temp": 28}},
            "covers": {},
            "switches": {},
        }
        resp = client.post("/home/snapshot", json=snapshot)
        assert resp.status_code == 200
        assert resp.json() == {"updated": True}

        resp = client.get("/home/")
        data = resp.json()
        assert data["bridge_connected"] is True
        assert data["lights"]["light.living_room"]["on"] is True


class TestHomeLightControl:
    def test_returns_503_without_ha_bridge(self, client):
        resp = client.post("/home/light/control", json={
            "entity_id": "light.living_room",
            "on": True,
        })
        assert resp.status_code == 503

    @patch("routers.home.HA_BRIDGE_URL", "http://fake-ha:8000")
    @patch("routers.home._ha_proxy_call", new_callable=AsyncMock)
    def test_light_toggle(self, mock_call, client):
        mock_call.return_value = {"success": True, "result": "light/turn_on -> light.living_room"}
        resp = client.post("/home/light/control", json={
            "entity_id": "light.living_room",
            "on": True,
            "brightness": 200,
        })
        assert resp.status_code == 200
        mock_call.assert_called_once()


class TestHomeClimateControl:
    def test_returns_503_without_ha_bridge(self, client):
        resp = client.post("/home/climate/control", json={
            "entity_id": "climate.living_room",
            "mode": "cool",
            "temperature": 26,
        })
        assert resp.status_code == 503


class TestHomeCoverControl:
    def test_returns_503_without_ha_bridge(self, client):
        resp = client.post("/home/cover/control", json={
            "entity_id": "cover.living_room",
            "action": "open",
        })
        assert resp.status_code == 503
