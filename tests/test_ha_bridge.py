"""
Tests for HEMS HA Bridge service.
"""
import sys
import importlib
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

_ha_src = str(Path(__file__).resolve().parent.parent / "services" / "ha-bridge" / "src")


def _ha_import(name: str):
    """Import a module from ha-bridge/src without polluting sys.path permanently."""
    # Temporarily add path, import, then clean up to avoid config collision
    old_config = sys.modules.pop("config", None)
    sys.path.insert(0, _ha_src)
    try:
        if name in sys.modules:
            del sys.modules[name]
        mod = importlib.import_module(name)
        return mod
    finally:
        sys.path.remove(_ha_src)
        # Restore previous config module if any
        if old_config is not None:
            sys.modules["config"] = old_config
        elif "config" in sys.modules and sys.modules["config"].__file__ and _ha_src in sys.modules["config"].__file__:
            del sys.modules["config"]


class TestEntityMapper:
    def test_default_mapping(self):
        mapper_mod = _ha_import("entity_mapper")
        mapper = mapper_mod.EntityMapper()

        zone, domain = mapper.map("light.living_room")
        assert zone == "living_room"
        assert domain == "light"

    def test_custom_mapping(self):
        mapper_mod = _ha_import("entity_mapper")
        mapper = mapper_mod.EntityMapper('{"light.my_light": {"zone": "bedroom", "domain": "light"}}')

        zone, domain = mapper.map("light.my_light")
        assert zone == "bedroom"
        assert domain == "light"

    def test_mqtt_topic(self):
        mapper_mod = _ha_import("entity_mapper")
        mapper = mapper_mod.EntityMapper()

        topic = mapper.get_mqtt_topic("light.living_room")
        assert topic == "hems/home/living_room/light/light.living_room/state"

    def test_invalid_entity_id(self):
        mapper_mod = _ha_import("entity_mapper")
        mapper = mapper_mod.EntityMapper()

        zone, domain = mapper.map("invalid")
        assert zone == "home"
        assert domain == "unknown"

    def test_invalid_json(self):
        mapper_mod = _ha_import("entity_mapper")
        mapper = mapper_mod.EntityMapper("not json")
        # Should fall through to default mapping
        zone, domain = mapper.map("light.test")
        assert domain == "light"


class TestHAClient:
    @pytest.mark.asyncio
    async def test_get_states_success(self):
        ha_mod = _ha_import("ha_client")
        client = ha_mod.HAClient("http://localhost:8123", "test-token")
        session = AsyncMock()

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=[
            {"entity_id": "light.test", "state": "on", "attributes": {}},
        ])
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        session.get = MagicMock(return_value=mock_resp)

        await client.start(session)
        states = await client.get_states()
        assert len(states) == 1
        assert states[0]["entity_id"] == "light.test"
        assert client.connected is True

    @pytest.mark.asyncio
    async def test_get_states_failure(self):
        ha_mod = _ha_import("ha_client")
        client = ha_mod.HAClient("http://localhost:8123", "test-token")
        session = AsyncMock()

        mock_resp = AsyncMock()
        mock_resp.status = 401
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        session.get = MagicMock(return_value=mock_resp)

        await client.start(session)
        states = await client.get_states()
        assert states == []

    @pytest.mark.asyncio
    async def test_call_service_success(self):
        ha_mod = _ha_import("ha_client")
        client = ha_mod.HAClient("http://localhost:8123", "test-token")
        session = AsyncMock()

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        session.post = MagicMock(return_value=mock_resp)

        await client.start(session)
        result = await client.call_service("light", "turn_on", "light.test", {"brightness": 200})
        assert result is True

    @pytest.mark.asyncio
    async def test_call_service_failure(self):
        ha_mod = _ha_import("ha_client")
        client = ha_mod.HAClient("http://localhost:8123", "test-token")
        session = AsyncMock()

        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        session.post = MagicMock(return_value=mock_resp)

        await client.start(session)
        result = await client.call_service("light", "turn_on", "light.test")
        assert result is False

    @pytest.mark.asyncio
    async def test_initial_state(self):
        ha_mod = _ha_import("ha_client")
        client = ha_mod.HAClient("http://localhost:8123", "token")
        assert client.connected is False
        assert client.url == "http://localhost:8123"


class TestMQTTPublisher:
    def test_publish(self):
        pub_mod = _ha_import("mqtt_publisher")
        pub = pub_mod.MQTTPublisher("localhost", 1883)
        pub.client = MagicMock()
        pub.publish("hems/home/test", {"state": "on"})
        pub.client.publish.assert_called_once()


class TestBridgeAPIEndpoints:
    @pytest.fixture
    def bridge_app(self):
        """Load ha-bridge main.py as a module and create test client."""
        spec = importlib.util.spec_from_file_location("ha_main", f"{_ha_src}/main.py")
        mod = importlib.util.module_from_spec(spec)

        # Pre-load dependencies
        old_config = sys.modules.pop("config", None)
        old_ha = sys.modules.pop("ha_client", None)
        old_mqtt = sys.modules.pop("mqtt_publisher", None)
        old_mapper = sys.modules.pop("entity_mapper", None)
        sys.path.insert(0, _ha_src)
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.path.remove(_ha_src)

        # Replace lifespan with noop
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        mod.app.router.lifespan_context = noop_lifespan
        # Restore modules
        for name, old in [("config", old_config), ("ha_client", old_ha),
                          ("mqtt_publisher", old_mqtt), ("entity_mapper", old_mapper)]:
            if old is not None:
                sys.modules[name] = old

        return mod

    def test_health_endpoint(self, bridge_app):
        from fastapi.testclient import TestClient
        client = TestClient(bridge_app.app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_devices_endpoint_503_when_not_initialized(self, bridge_app):
        from fastapi.testclient import TestClient
        bridge_app.ha_client = None
        client = TestClient(bridge_app.app)
        resp = client.get("/api/devices")
        assert resp.status_code == 503

    def test_device_control_503_when_not_initialized(self, bridge_app):
        from fastapi.testclient import TestClient
        bridge_app.ha_client = None
        client = TestClient(bridge_app.app)
        resp = client.post("/api/device/control", json={
            "entity_id": "light.test",
            "service": "light/turn_on",
            "data": {},
        })
        assert resp.status_code == 503
