"""
W1.2 — device_id / vendor_ref character-set validation tests.

Covers:
  (a) Backend /devices/ create (POST) — rejects bad device_id / vendor_ref with 422
  (b) Backend /devices/heartbeat (POST) — rejects bad device_id / vendor_ref with 422
  (c) DeviceDispatcher.dispatch() — rejects bad device_id before lookup
  (d) DeviceDispatcher._dispatch_zigbee() — rejects bad vendor_ref before MQTT publish
  (e) DeviceDispatcher._dispatch_switchbot() — rejects bad vendor_ref before URL assembly
  (f) DeviceDispatcher._dispatch_tapo() — rejects bad vendor_ref before URL assembly
  (g) Positive: real-world identifiers accepted (zigbee IEEE addr, switchbot, tapo, ha, mcp)
  (h) device_id_validator module — unit tests for is_valid_device_ref()
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure both source trees are importable ─────────────────────────────────
_root = Path(__file__).resolve().parent.parent
_brain_src = _root / "services" / "brain" / "src"
_backend_src = _root / "services" / "backend"
for _p in (_brain_src, _backend_src):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def devices_client(tmp_path, monkeypatch):
    """FastAPI TestClient wired to an in-memory devices router with real DB."""
    import asyncio

    db_file = tmp_path / "hems_dev_val_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")

    # Evict any cached backend modules so they re-import with the test DB URL.
    for mod in list(sys.modules.keys()):
        if mod in ("database", "models", "schemas", "routers.devices", "auth"):
            del sys.modules[mod]

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import database
    from routers.devices import router

    app = FastAPI()
    app.include_router(router)

    asyncio.run(_create_tables(database))

    return TestClient(app)


async def _create_tables(db_module):
    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.create_all)


# ─────────────────────────────────────────────────────────────────────────────
# (h) Unit tests — device_id_validator.is_valid_device_ref()
# ─────────────────────────────────────────────────────────────────────────────


class TestIsValidDeviceRef:
    def setup_method(self):
        from device_id_validator import is_valid_device_ref

        self.check = is_valid_device_ref

    # --- invalid ---

    def test_empty_string_rejected(self):
        assert self.check("") is False

    def test_slash_rejected(self):
        assert self.check("foo/bar") is False

    def test_dotdot_rejected(self):
        assert self.check("../etc/passwd") is False

    def test_wildcard_plus_rejected(self):
        assert self.check("zigbee.+") is False

    def test_wildcard_hash_rejected(self):
        assert self.check("zigbee.#") is False

    def test_space_rejected(self):
        assert self.check("foo bar") is False

    def test_null_byte_rejected(self):
        assert self.check("foo\x00bar") is False

    def test_exceeds_max_length_rejected(self):
        from device_id_validator import DEVICE_ID_MAX_LEN

        assert self.check("a" * (DEVICE_ID_MAX_LEN + 1)) is False

    def test_exactly_max_length_accepted(self):
        from device_id_validator import DEVICE_ID_MAX_LEN

        assert self.check("a" * DEVICE_ID_MAX_LEN) is True

    # --- valid real-world formats ---

    def test_zigbee_ieee_address(self):
        # Real Zigbee device from zigbee2mqtt
        assert self.check("0x00124b0025ad1234") is True

    def test_zigbee_friendly_name(self):
        assert self.check("living_room_bulb") is True

    def test_zigbee_prefixed_device_id(self):
        assert self.check("zigbee.0x00124b0025ad1234") is True

    def test_switchbot_abc_format(self):
        # SwitchBot device IDs: uppercase hex with hyphens
        assert self.check("switchbot.ABC-123") is True

    def test_switchbot_mac_like(self):
        assert self.check("E4-AB-89-FE-BC-12") is True

    def test_tapo_ip_like(self):
        # Tapo vendor_refs are IP addresses or device labels
        assert self.check("192.168.1.100") is True

    def test_ha_entity_id(self):
        assert self.check("light.living_room") is True

    def test_ha_climate_entity(self):
        assert self.check("climate.air_conditioner") is True

    def test_mcp_sensor(self):
        assert self.check("mcp.co2_sensor_desk") is True

    def test_simple_alphanumeric(self):
        assert self.check("device123") is True

    def test_underscores_and_dots(self):
        assert self.check("plug_desk.v2") is True

    def test_none_is_false(self):
        # None is only acceptable in optional fields (handled upstream); the
        # low-level function itself returns False for None.
        assert self.check(None) is False  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────────────
# (a) Backend POST /devices/ — create
# ─────────────────────────────────────────────────────────────────────────────


class TestBackendCreateDevice:
    def test_valid_device_accepted(self, devices_client):
        resp = devices_client.post(
            "/devices/",
            json={
                "device_id": "zigbee.0x00124b0025ad1234",
                "vendor": "zigbee",
                "vendor_ref": "0x00124b0025ad1234",
            },
        )
        assert resp.status_code == 200

    def test_path_traversal_in_device_id_rejected(self, devices_client):
        resp = devices_client.post(
            "/devices/",
            json={"device_id": "../etc/passwd", "vendor": "zigbee"},
        )
        assert resp.status_code == 422

    def test_empty_device_id_rejected(self, devices_client):
        resp = devices_client.post(
            "/devices/",
            json={"device_id": "", "vendor": "zigbee"},
        )
        assert resp.status_code == 422

    def test_slash_in_device_id_rejected(self, devices_client):
        resp = devices_client.post(
            "/devices/",
            json={"device_id": "foo/bar", "vendor": "zigbee"},
        )
        assert resp.status_code == 422

    def test_mqtt_wildcard_plus_in_device_id_rejected(self, devices_client):
        resp = devices_client.post(
            "/devices/",
            json={"device_id": "zigbee.+", "vendor": "zigbee"},
        )
        assert resp.status_code == 422

    def test_mqtt_wildcard_hash_in_device_id_rejected(self, devices_client):
        resp = devices_client.post(
            "/devices/",
            json={"device_id": "zigbee.#", "vendor": "zigbee"},
        )
        assert resp.status_code == 422

    def test_slash_in_vendor_ref_rejected(self, devices_client):
        resp = devices_client.post(
            "/devices/",
            json={
                "device_id": "zigbee.safe",
                "vendor": "zigbee",
                "vendor_ref": "../../inject",
            },
        )
        assert resp.status_code == 422

    def test_none_vendor_ref_accepted(self, devices_client):
        """vendor_ref is optional — None must be accepted."""
        resp = devices_client.post(
            "/devices/",
            json={"device_id": "switchbot.ABC-001", "vendor": "switchbot"},
        )
        assert resp.status_code == 200

    def test_switchbot_abc_vendor_ref_accepted(self, devices_client):
        resp = devices_client.post(
            "/devices/",
            json={
                "device_id": "switchbot.ABC-123",
                "vendor": "switchbot",
                "vendor_ref": "ABC-123",
            },
        )
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# (b) Backend POST /devices/heartbeat
# ─────────────────────────────────────────────────────────────────────────────


class TestBackendHeartbeat:
    def test_valid_heartbeat_accepted(self, devices_client):
        resp = devices_client.post(
            "/devices/heartbeat",
            json={
                "device_id": "tapo.192.168.1.50",
                "vendor": "tapo",
                "vendor_ref": "192.168.1.50",
            },
        )
        assert resp.status_code == 200

    def test_bad_device_id_rejected(self, devices_client):
        resp = devices_client.post(
            "/devices/heartbeat",
            json={"device_id": "bad/device", "vendor": "zigbee"},
        )
        assert resp.status_code == 422

    def test_empty_device_id_rejected(self, devices_client):
        resp = devices_client.post(
            "/devices/heartbeat",
            json={"device_id": "", "vendor": "zigbee"},
        )
        assert resp.status_code == 422

    def test_bad_vendor_ref_rejected(self, devices_client):
        resp = devices_client.post(
            "/devices/heartbeat",
            json={
                "device_id": "zigbee.safe",
                "vendor": "zigbee",
                "vendor_ref": "mqtt/injection#attempt",
            },
        )
        assert resp.status_code == 422

    def test_wildcard_in_heartbeat_device_id_rejected(self, devices_client):
        resp = devices_client.post(
            "/devices/heartbeat",
            json={"device_id": "zigbee.+", "vendor": "zigbee"},
        )
        assert resp.status_code == 422

    def test_real_ha_entity_accepted(self, devices_client):
        resp = devices_client.post(
            "/devices/heartbeat",
            json={
                "device_id": "ha.light.living_room",
                "vendor": "ha",
                "vendor_ref": "light.living_room",
            },
        )
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# (c) DeviceDispatcher.dispatch() — pre-lookup validation
# ─────────────────────────────────────────────────────────────────────────────


class TestDispatcherDispatchValidation:
    """dispatch() must reject invalid device_id before any network I/O."""

    def _make_dispatcher(self):
        import aiohttp

        from device_dispatcher import DeviceDispatcher

        session = MagicMock(spec=aiohttp.ClientSession)
        dispatcher = DeviceDispatcher(session=session, mqtt_client=None)
        return dispatcher

    @pytest.mark.asyncio
    async def test_path_traversal_device_id_rejected(self):
        dispatcher = self._make_dispatcher()
        result = await dispatcher.dispatch("../etc/passwd", "on")
        assert result["success"] is False
        assert "Invalid device_id" in result["error"]

    @pytest.mark.asyncio
    async def test_slash_device_id_rejected(self):
        dispatcher = self._make_dispatcher()
        result = await dispatcher.dispatch("foo/bar", "on")
        assert result["success"] is False
        assert "Invalid device_id" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_device_id_rejected(self):
        dispatcher = self._make_dispatcher()
        result = await dispatcher.dispatch("", "on")
        assert result["success"] is False
        assert "Invalid device_id" in result["error"]

    @pytest.mark.asyncio
    async def test_mqtt_wildcard_plus_rejected(self):
        dispatcher = self._make_dispatcher()
        result = await dispatcher.dispatch("zigbee.+", "on")
        assert result["success"] is False
        assert "Invalid device_id" in result["error"]

    @pytest.mark.asyncio
    async def test_mqtt_wildcard_hash_rejected(self):
        dispatcher = self._make_dispatcher()
        result = await dispatcher.dispatch("zigbee.#", "on")
        assert result["success"] is False
        assert "Invalid device_id" in result["error"]

    @pytest.mark.asyncio
    async def test_valid_device_id_passes_to_lookup(self):
        """A valid device_id must NOT be blocked — it proceeds to lookup()."""
        import aiohttp

        from device_dispatcher import DeviceDispatcher

        session = MagicMock(spec=aiohttp.ClientSession)
        dispatcher = DeviceDispatcher(session=session, mqtt_client=None)

        # Patch lookup to return None (not registered) — proves validation passed
        dispatcher.lookup = AsyncMock(return_value=None)
        result = await dispatcher.dispatch("zigbee.0x00124b0025ad1234", "on")
        dispatcher.lookup.assert_awaited_once()
        assert "not registered" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# (d) _dispatch_zigbee() — vendor_ref guard before MQTT publish
# ─────────────────────────────────────────────────────────────────────────────


class TestDispatchZigbeeValidation:
    def _make_dispatcher(self):
        import aiohttp

        from device_dispatcher import DeviceDispatcher

        mqtt_client = MagicMock()
        session = MagicMock(spec=aiohttp.ClientSession)
        return DeviceDispatcher(session=session, mqtt_client=mqtt_client), mqtt_client

    def test_bad_vendor_ref_rejected(self):
        dispatcher, mqtt = self._make_dispatcher()
        result = dispatcher._dispatch_zigbee(
            {"vendor_ref": "mqtt/injection#attempt", "device_id": "zigbee.bad"},
            "on",
            {},
        )
        assert result["success"] is False
        assert "Invalid vendor_ref" in result["error"]
        mqtt.publish.assert_not_called()

    def test_path_traversal_vendor_ref_rejected(self):
        dispatcher, mqtt = self._make_dispatcher()
        result = dispatcher._dispatch_zigbee(
            {"vendor_ref": "../private", "device_id": "zigbee.bad"},
            "on",
            {},
        )
        assert result["success"] is False
        mqtt.publish.assert_not_called()

    def test_valid_ieee_addr_vendor_ref_accepted(self):
        dispatcher, mqtt = self._make_dispatcher()
        result = dispatcher._dispatch_zigbee(
            {"vendor_ref": "0x00124b0025ad1234", "device_id": "zigbee.0x00124b0025ad1234"},
            "on",
            {},
        )
        assert result["success"] is True
        mqtt.publish.assert_called_once()
        topic = mqtt.publish.call_args[0][0]
        assert topic == "zigbee2mqtt/0x00124b0025ad1234/set"

    def test_valid_friendly_name_accepted(self):
        dispatcher, _mqtt = self._make_dispatcher()
        result = dispatcher._dispatch_zigbee(
            {"vendor_ref": "living_room_bulb", "device_id": "zigbee.living_room_bulb"},
            "off",
            {},
        )
        assert result["success"] is True


# ─────────────────────────────────────────────────────────────────────────────
# (e) _dispatch_switchbot() — vendor_ref guard before HTTP URL assembly
# ─────────────────────────────────────────────────────────────────────────────


class TestDispatchSwitchbotValidation:
    def _make_dispatcher(self, monkeypatch=None):
        import aiohttp

        import device_dispatcher as dd
        from device_dispatcher import DeviceDispatcher

        if monkeypatch:
            monkeypatch.setattr(dd, "SWITCHBOT_BRIDGE_URL", "http://switchbot-bridge:8000")
        else:
            dd.SWITCHBOT_BRIDGE_URL = "http://switchbot-bridge:8000"

        session = MagicMock(spec=aiohttp.ClientSession)
        return DeviceDispatcher(session=session, mqtt_client=None)

    @pytest.mark.asyncio
    async def test_bad_vendor_ref_rejected(self):
        import device_dispatcher as dd

        dd.SWITCHBOT_BRIDGE_URL = "http://switchbot-bridge:8000"
        import aiohttp

        from device_dispatcher import DeviceDispatcher

        dispatcher = DeviceDispatcher(session=MagicMock(spec=aiohttp.ClientSession), mqtt_client=None)
        result = await dispatcher._dispatch_switchbot(
            {"vendor_ref": "../../../etc/passwd", "device_id": "switchbot.bad"},
            "on",
            {},
        )
        assert result["success"] is False
        assert "Invalid vendor_ref" in result["error"]

    @pytest.mark.asyncio
    async def test_valid_abc_vendor_ref_format(self):
        """ABC-123 style SwitchBot IDs must be accepted."""
        import device_dispatcher as dd

        dd.SWITCHBOT_BRIDGE_URL = "http://switchbot-bridge:8000"
        import aiohttp

        from device_dispatcher import DeviceDispatcher

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock(spec=aiohttp.ClientSession)
        session.post = MagicMock(return_value=mock_resp)

        dispatcher = DeviceDispatcher(session=session, mqtt_client=None)
        result = await dispatcher._dispatch_switchbot(
            {"vendor_ref": "ABC-123", "device_id": "switchbot.ABC-123"},
            "on",
            {},
        )
        assert result["success"] is True


# ─────────────────────────────────────────────────────────────────────────────
# (f) _dispatch_tapo() — vendor_ref guard before HTTP URL assembly
# ─────────────────────────────────────────────────────────────────────────────


class TestDispatchTapoValidation:
    @pytest.mark.asyncio
    async def test_bad_vendor_ref_rejected(self):
        import device_dispatcher as dd

        dd.TAPO_BRIDGE_URL = "http://tapo-bridge:8000"
        import aiohttp

        from device_dispatcher import DeviceDispatcher

        dispatcher = DeviceDispatcher(session=MagicMock(spec=aiohttp.ClientSession), mqtt_client=None)
        result = await dispatcher._dispatch_tapo(
            {"vendor_ref": "bad/path", "device_id": "tapo.bad"},
            "on",
            {},
        )
        assert result["success"] is False
        assert "Invalid vendor_ref" in result["error"]

    @pytest.mark.asyncio
    async def test_valid_ip_vendor_ref_accepted(self):
        """IP address vendor_refs (Tapo uses IPs) must be accepted."""
        import device_dispatcher as dd

        dd.TAPO_BRIDGE_URL = "http://tapo-bridge:8000"
        import aiohttp

        from device_dispatcher import DeviceDispatcher

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock(spec=aiohttp.ClientSession)
        session.post = MagicMock(return_value=mock_resp)

        dispatcher = DeviceDispatcher(session=session, mqtt_client=None)
        result = await dispatcher._dispatch_tapo(
            {"vendor_ref": "192.168.1.100", "device_id": "tapo.192.168.1.100"},
            "on",
            {},
        )
        assert result["success"] is True
