"""
Tests for backend home (HA control) router — in-memory store + httpx proxy.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    """Create a test client for the home router with HA_BRIDGE_URL isolated."""
    monkeypatch.delenv("HA_BRIDGE_URL", raising=False)
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
        resp = client.post(
            "/home/light/control",
            json={
                "entity_id": "light.living_room",
                "on": True,
            },
        )
        assert resp.status_code == 503

    @patch("routers.home._ha_proxy_call", new_callable=AsyncMock)
    def test_light_toggle(self, mock_call, client, monkeypatch):
        monkeypatch.setenv("HA_BRIDGE_URL", "http://fake-ha:8000")
        mock_call.return_value = {"success": True, "result": "light/turn_on -> light.living_room"}
        resp = client.post(
            "/home/light/control",
            json={
                "entity_id": "light.living_room",
                "on": True,
                "brightness": 200,
            },
        )
        assert resp.status_code == 200
        mock_call.assert_called_once()


class TestHomeClimateControl:
    def test_returns_503_without_ha_bridge(self, client):
        resp = client.post(
            "/home/climate/control",
            json={
                "entity_id": "climate.living_room",
                "mode": "cool",
                "temperature": 26,
            },
        )
        assert resp.status_code == 503


class TestHomeCoverControl:
    def test_returns_503_without_ha_bridge(self, client):
        resp = client.post(
            "/home/cover/control",
            json={
                "entity_id": "cover.living_room",
                "action": "open",
            },
        )
        assert resp.status_code == 503


class TestHomeInternalAuthHeaders:
    @pytest.mark.asyncio
    async def test_ha_proxy_call_includes_bearer_token(self, monkeypatch):
        monkeypatch.setenv("HA_BRIDGE_URL", "http://fake-ha:8000")
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret-token")

        from routers.home import _ha_proxy_call

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = "ok"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
            result = await _ha_proxy_call("light.living_room", "light/turn_on")
            assert result["success"] is True
            mock_post.assert_awaited_once()
            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["headers"]["Authorization"] == "Bearer secret-token"

    @pytest.mark.asyncio
    async def test_get_home_devices_includes_bearer_token(self, monkeypatch):
        monkeypatch.setenv("HA_BRIDGE_URL", "http://fake-ha:8000")
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret-token")

        from routers.home import get_home_devices

        mock_resp = AsyncMock()
        mock_resp.json = Mock(return_value={"devices": []})

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp) as mock_get:
            result = await get_home_devices()
            assert result == {"devices": []}
            mock_get.assert_awaited_once()
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["headers"]["Authorization"] == "Bearer secret-token"

    @pytest.mark.asyncio
    async def test_ha_proxy_call_omits_auth_when_token_unset(self, monkeypatch):
        monkeypatch.setenv("HA_BRIDGE_URL", "http://fake-ha:8000")
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)

        from routers.home import _ha_proxy_call

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = "ok"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
            await _ha_proxy_call("light.living_room", "light/turn_on")
            call_kwargs = mock_post.call_args.kwargs
            assert "Authorization" not in call_kwargs.get("headers", {})
