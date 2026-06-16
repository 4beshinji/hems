"""
W3.4 — Characterization tests for device_dispatcher.py (C1, pre-split).

Purpose: pin the *current* observed behaviour of dispatch happy-paths,
parse_mqtt field values, and special mechanisms (pulse / rainbow / tapo_raw)
so that the C2 vendor-parser split can proceed without silent regressions.

IMPORTANT: These tests MUST stay green against the unmodified production code.
Do NOT edit production code (services/) to make these pass — if a test fails
on an unmodified tree, the test expectation is wrong.

Coverage targets (§7.3 of W3.4 design note):
  A. parse_mqtt happy-path — all 5 vendor topic patterns, full field assertion
  B. parse_z2m_bridge_devices — light / sensor / friendly-name / raw-IEEE / no-def
  C. dispatch → publish/POST pin per vendor × action
  D. Action / capability guard paths
  E. Error formatting: bridge 4xx detail extraction, _tapo_raw exception→error
  F. Special mechanisms: pulse (tapo & zigbee), rainbow (ha & zigbee), zigbee_permit_join
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Path setup ───────────────────────────────────────────────────────────────
_root = Path(__file__).resolve().parent.parent
for _p in (
    _root / "services" / "brain" / "src",
    _root / "services" / "backend",
    _root / "services" / "_common",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ── Module-level skip guard ───────────────────────────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def _require_device_dispatcher():
    pytest.importorskip("device_dispatcher", reason="device_dispatcher not importable")


# ── Shared helpers ────────────────────────────────────────────────────────────


def _make_dispatcher(
    ha_url: str = "",
    switchbot_url: str = "",
    tapo_url: str = "",
    mqtt_client=None,
):
    """Build a DeviceDispatcher with mocked session and optionally bridge URLs."""
    import aiohttp

    import device_dispatcher as dd
    from device_dispatcher import DeviceDispatcher

    dd.HA_BRIDGE_URL = ha_url
    dd.SWITCHBOT_BRIDGE_URL = switchbot_url
    dd.TAPO_BRIDGE_URL = tapo_url

    session = MagicMock(spec=aiohttp.ClientSession)
    if mqtt_client is None:
        mqtt_client = MagicMock()
    return DeviceDispatcher(session=session, mqtt_client=mqtt_client), session, mqtt_client


def _ok_response(json_data=None, status=200):
    """Build a mock async context-manager response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.read = AsyncMock(return_value=b"")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _err_response(status=422, detail="bad request"):
    return _ok_response(json_data={"detail": detail}, status=status)


# =============================================================================
# A. parse_mqtt — happy-path field pinning
# =============================================================================


class TestParseMqttMcp:
    """hems/sensors/{zone}/sensor/{device_id}/{channel}"""

    def _parse(self, topic, payload=None):
        from device_dispatcher import parse_mqtt

        return parse_mqtt(topic, payload or {})

    def test_temperature_channel_fields(self):
        obs = self._parse(
            "hems/sensors/living/sensor/co2_desk/temperature",
            {"temperature": 23.5},
        )
        assert obs is not None
        assert obs.device_id == "mcp.co2_desk"
        assert obs.vendor == "mcp"
        assert obs.vendor_ref == "co2_desk"
        assert obs.kind == "sensor"
        assert obs.device_class == "temp_humidity"
        assert obs.channels == ["temperature"]
        assert obs.units == {"temperature": "°C"}
        assert obs.zone == "living"
        assert obs.last_value == {"temperature": 23.5}

    def test_co2_channel_fields(self):
        obs = self._parse(
            "hems/sensors/desk/sensor/air_monitor/co2",
            {"co2": 850},
        )
        assert obs is not None
        assert obs.device_id == "mcp.air_monitor"
        assert obs.device_class == "co2"
        assert obs.channels == ["co2"]
        assert obs.units == {"co2": "ppm"}
        assert obs.last_value == {"co2": 850.0}

    def test_value_key_fallback(self):
        """Payload with generic 'value' key (no channel key)."""
        obs = self._parse(
            "hems/sensors/bed/sensor/soil_probe/soil_moisture",
            {"value": 42.0},
        )
        assert obs is not None
        assert obs.last_value == {"soil_moisture": 42.0}

    def test_unknown_channel_no_unit(self):
        obs = self._parse(
            "hems/sensors/hall/sensor/motion1/pir",
            {"pir": 1},
        )
        assert obs is not None
        assert obs.channels == ["pir"]
        assert obs.units == {}

    def test_humidity_unit(self):
        obs = self._parse(
            "hems/sensors/kitchen/sensor/humidity_wall/humidity",
            {"humidity": 55.0},
        )
        assert obs.units == {"humidity": "%"}

    def test_pm25_no_unit_registered(self):
        obs = self._parse(
            "hems/sensors/living/sensor/air_q/pm25",
            {"pm25": 12},
        )
        # pm25 not in _SENSOR_CHANNEL_UNITS but not in units mapping either → no unit entry
        # (pm25 IS in _SENSOR_CHANNEL_UNITS with unit µg/m³)
        assert obs.units.get("pm25") == "µg/m³"


class TestParseMqttSwitchbot:
    """hems/switchbot/{device_id}/state"""

    def _parse(self, ref, payload=None):
        from device_dispatcher import parse_mqtt

        return parse_mqtt(f"hems/switchbot/{ref}/state", payload or {})

    def test_plug_device(self):
        obs = self._parse(
            "ABC-123",
            {"device_type": "Plug", "state": "on", "battery": 80, "rssi": -60},
        )
        assert obs is not None
        assert obs.device_id == "switchbot.ABC-123"
        assert obs.vendor == "switchbot"
        assert obs.vendor_ref == "ABC-123"
        assert obs.kind == "both"
        assert obs.device_class == "plug"
        assert "on_off" in obs.capabilities
        assert "pulse" in obs.capabilities
        assert obs.last_state == {"on": True}
        assert obs.battery_pct == 80
        assert obs.link_quality == -60

    def test_curtain_device(self):
        obs = self._parse(
            "CURTAIN-001",
            {"device_type": "Curtain", "state": "on"},
        )
        assert obs.device_class == "curtain"
        assert "set_position" in obs.capabilities

    def test_hub_device(self):
        obs = self._parse(
            "HUB-001",
            {"device_type": "Hub Plus"},
        )
        assert obs.device_class == "hub_ir"
        assert "ir_send" in obs.capabilities

    def test_state_off(self):
        obs = self._parse("DEV-001", {"device_type": "Plug", "state": "off"})
        assert obs.last_state == {"on": False}

    def test_zone_propagated(self):
        obs = self._parse("DEV-002", {"device_type": "Switch", "zone": "bedroom"})
        assert obs.zone == "bedroom"


class TestParseMqttTapo:
    """hems/tapo/{device_id}/state"""

    def _parse(self, ref, payload=None):
        from device_dispatcher import parse_mqtt

        return parse_mqtt(f"hems/tapo/{ref}/state", payload or {})

    def test_basic_fields(self):
        obs = self._parse(
            "192.168.1.50",
            {"state": "on", "power_watts": 12.5, "voltage": 220.0},
        )
        assert obs is not None
        assert obs.device_id == "tapo.192.168.1.50"
        assert obs.vendor == "tapo"
        assert obs.vendor_ref == "192.168.1.50"
        assert obs.kind == "both"
        assert obs.device_class == "plug"
        assert obs.capabilities == ["on_off", "pulse"]
        assert obs.last_state == {"on": True}
        assert obs.last_value == {"power_watts": 12.5, "voltage": 220.0}

    def test_bool_state_on(self):
        obs = self._parse("192.168.1.51", {"on": True})
        assert obs.last_state == {"on": True}

    def test_energy_fields_propagated(self):
        obs = self._parse(
            "192.168.1.52",
            {"state": "off", "energy_kwh": 1.23, "current": 0.05},
        )
        assert obs.last_value == {"energy_kwh": 1.23, "current": 0.05}


class TestParseMqttZigbee:
    """zigbee2mqtt/{device}"""

    def _parse(self, ref, payload=None):
        from device_dispatcher import parse_mqtt

        return parse_mqtt(f"zigbee2mqtt/{ref}", payload or {})

    def test_light_on_off_brightness_colortemp(self):
        obs = self._parse(
            "living_room_bulb",
            {"state": "ON", "brightness": 200, "color_temp": 300},
        )
        assert obs is not None
        assert obs.device_id == "zigbee.living_room_bulb"
        assert obs.vendor == "zigbee"
        assert obs.vendor_ref == "living_room_bulb"
        assert obs.kind == "actuator"
        assert obs.device_class == "light"
        assert set(obs.capabilities) == {"on_off", "brightness", "color_temp"}
        assert obs.last_state == {"on": True, "brightness": 200, "color_temp": 300}

    def test_light_color_xy(self):
        obs = self._parse(
            "0x00124b0025ad1234",
            {"state": "ON", "brightness": 254, "color": {"x": 0.312, "y": 0.329}},
        )
        assert "color_xy" in obs.capabilities
        assert obs.last_state["color_xy"] == {"x": 0.312, "y": 0.329}

    def test_light_color_hs(self):
        obs = self._parse(
            "desk_bulb",
            {"state": "ON", "color": {"hue": 120.0, "saturation": 80}},
        )
        assert "color_hs" in obs.capabilities
        assert obs.last_state["color_hs"] == {"hue": 120.0, "saturation": 80}

    def test_sensor_only_kind(self):
        obs = self._parse(
            "temp_sensor_01",
            {"temperature": 22.1, "humidity": 55.0, "battery": 75, "linkquality": 100},
        )
        assert obs.kind == "sensor"
        assert obs.device_class == "temp_humidity"
        assert set(obs.channels) == {"temperature", "humidity"}
        assert obs.last_value["temperature"] == 22.1
        assert obs.battery_pct == 75
        assert obs.link_quality == 100

    def test_plug_no_sensor(self):
        obs = self._parse("outlet_01", {"state": "OFF"})
        assert obs.device_class == "plug"
        assert obs.kind == "actuator"

    def test_state_off(self):
        obs = self._parse("plug_01", {"state": "OFF"})
        assert obs.last_state == {"on": False}

    def test_bridge_topic_returns_none(self):
        from device_dispatcher import parse_mqtt

        assert parse_mqtt("zigbee2mqtt/bridge/devices", {}) is None
        assert parse_mqtt("zigbee2mqtt/bridge/state", {}) is None


class TestParseMqttHa:
    """hems/home/{zone}/{domain}/{entity_id}/state"""

    def _parse(self, zone, domain, entity, payload=None):
        from device_dispatcher import parse_mqtt

        topic = f"hems/home/{zone}/{domain}/{entity}/state"
        return parse_mqtt(topic, payload or {})

    def test_light_entity(self):
        obs = self._parse(
            "living",
            "light",
            "ceiling",
            {"state": "on", "brightness": 180, "color_temp": 350},
        )
        assert obs is not None
        assert obs.device_id == "ha.light.ceiling"
        assert obs.vendor == "ha"
        assert obs.vendor_ref == "light.ceiling"
        assert obs.kind == "actuator"
        assert obs.device_class == "light"
        assert "on_off" in obs.capabilities
        assert "brightness" in obs.capabilities
        assert "color_temp" in obs.capabilities
        assert obs.zone == "living"
        assert obs.last_state == {"on": True, "brightness": 180, "color_temp": 350}

    def test_switch_entity(self):
        obs = self._parse(
            "kitchen",
            "switch",
            "fan",
            {"state": "off"},
        )
        assert obs.device_class == "plug"
        assert obs.kind == "actuator"
        assert set(obs.capabilities) == {"on_off", "pulse"}
        assert obs.last_state == {"on": False}

    def test_climate_entity(self):
        obs = self._parse(
            "bed",
            "climate",
            "aircon",
            {"state": "cool", "current_temperature": 24.5, "hvac_mode": "cool"},
        )
        assert obs.device_class == "climate"
        assert obs.kind == "actuator"
        assert "set_temperature" in obs.capabilities
        assert obs.last_state["hvac_mode"] == "cool"
        assert obs.last_state["current_temperature"] == 24.5

    def test_cover_entity(self):
        obs = self._parse(
            "living",
            "cover",
            "blinds",
            {"state": "closed", "current_position": 0},
        )
        assert obs.device_class == "curtain"
        assert obs.kind == "actuator"
        assert "set_position" in obs.capabilities
        assert obs.last_state["position"] == 0

    def test_sensor_entity_kind(self):
        obs = self._parse(
            "hall",
            "sensor",
            "motion_01",
            {"state": "detected", "device_class": "motion"},
        )
        assert obs.kind == "sensor"
        assert obs.device_class == "motion"

    def test_entity_id_from_payload_overrides_topic(self):
        """If payload carries entity_id, that wins over domain.entity reconstruction."""
        obs = self._parse(
            "living",
            "light",
            "ceiling",
            {"entity_id": "light.ceiling_v2", "state": "on"},
        )
        assert obs.vendor_ref == "light.ceiling_v2"
        assert obs.device_id == "ha.light.ceiling_v2"

    def test_unmatched_topic_returns_none(self):
        from device_dispatcher import parse_mqtt

        assert parse_mqtt("hems/other/topic", {}) is None


# =============================================================================
# B. parse_z2m_bridge_devices — field pinning
# =============================================================================


class TestParseZ2mBridgeDevices:
    def _parse(self, payload):
        from device_dispatcher import parse_z2m_bridge_devices

        return parse_z2m_bridge_devices(payload)

    def _light_def(self, friendly, model="TRADFRI bulb", vendor="IKEA", desc="TRADFRI LED bulb"):
        return {
            "friendly_name": friendly,
            "definition": {
                "model": model,
                "vendor": vendor,
                "description": desc,
                "exposes": [
                    {
                        "type": "light",
                        "features": [
                            {"name": "state"},
                            {"name": "brightness"},
                            {"name": "color_temp"},
                        ],
                    }
                ],
            },
        }

    def _sensor_def(self, friendly, fname="temperature"):
        return {
            "friendly_name": friendly,
            "definition": {
                "model": "ZG-102ZM",
                "vendor": "HOBEIAN",
                "description": "Vibration sensor",
                "exposes": [
                    {"type": "numeric", "name": fname},
                ],
            },
        }

    def test_light_device_capabilities(self):
        obs_list = self._parse([self._light_def("living_lamp")])
        assert len(obs_list) == 1
        obs = obs_list[0]
        assert obs.device_id == "zigbee.living_lamp"
        assert obs.vendor == "zigbee"
        assert obs.vendor_ref == "living_lamp"
        assert obs.kind == "actuator"
        assert obs.device_class == "light"
        assert set(obs.capabilities) == {"on_off", "brightness", "color_temp"}
        assert obs.display_name == "living_lamp"  # friendly name kept (not IEEE)

    def test_sensor_device_channels(self):
        obs_list = self._parse([self._sensor_def("temp_sensor_01", "temperature")])
        assert len(obs_list) == 1
        obs = obs_list[0]
        assert obs.device_class == "climate"
        assert "temperature" in obs.channels

    def test_occupancy_sensor(self):
        payload = [
            {
                "friendly_name": "motion_hall",
                "definition": {
                    "model": "S40ZBTPB",
                    "vendor": "Sonoff",
                    "description": "Motion sensor",
                    "exposes": [{"type": "binary", "name": "occupancy"}],
                },
            }
        ]
        obs_list = self._parse(payload)
        assert len(obs_list) == 1
        obs = obs_list[0]
        assert obs.device_class == "motion"
        assert "occupancy" in obs.channels

    def test_coordinator_skipped(self):
        obs_list = self._parse(
            [
                {
                    "friendly_name": "Coordinator",
                    "definition": {"model": "CC2652P", "vendor": "TI", "description": "Coordinator", "exposes": []},
                }
            ]
        )
        assert obs_list == []

    def test_no_definition_skipped(self):
        obs_list = self._parse([{"friendly_name": "unknown_dev", "definition": {}}])
        assert obs_list == []

    def test_raw_ieee_display_name(self):
        """A device whose friendly_name IS an IEEE addr gets label from description."""
        ieee = "0x00124b0025ad1234"
        payload = [
            {
                "friendly_name": ieee,
                "definition": {
                    "model": "ZG-102ZM",
                    "vendor": "HOBEIAN",
                    "description": "Vibration sensor",
                    "exposes": [{"type": "binary", "name": "vibration"}],
                },
            }
        ]
        obs_list = self._parse(payload)
        assert len(obs_list) == 1
        obs = obs_list[0]
        # Display name should incorporate last 6 of IEEE
        assert ieee[-6:] in obs.display_name

    def test_friendly_name_not_ieee_kept_as_display(self):
        obs_list = self._parse([self._light_def("bedroom_ceiling")])
        assert obs_list[0].display_name == "bedroom_ceiling"

    def test_no_device_class_after_expose_parse_skipped(self):
        """A device with exposes that produce no device_class is skipped."""
        payload = [
            {
                "friendly_name": "mystery_device",
                "definition": {
                    "model": "XYZ",
                    "vendor": "Unknown",
                    "description": "Unknown device",
                    "exposes": [],  # no exposes → no device_class
                },
            }
        ]
        obs_list = self._parse(payload)
        assert obs_list == []

    def test_manufacturer_and_model_stored(self):
        obs_list = self._parse([self._light_def("lamp", model="L530E", vendor="IKEA", desc="Smart bulb")])
        obs = obs_list[0]
        assert obs.manufacturer == "IKEA"
        assert obs.model_id == "L530E"

    def test_mixed_light_and_sensor_kind_both(self):
        """A device exposing both a light type and an occupancy sensor → kind='both'."""
        payload = [
            {
                "friendly_name": "combo_dev",
                "definition": {
                    "model": "HB-001",
                    "vendor": "Acme",
                    "description": "Light with occupancy",
                    "exposes": [
                        {
                            "type": "light",
                            "features": [{"name": "state"}, {"name": "brightness"}],
                        },
                        {"type": "binary", "name": "occupancy"},
                    ],
                },
            }
        ]
        obs_list = self._parse(payload)
        assert len(obs_list) == 1
        obs = obs_list[0]
        assert obs.kind == "both"
        assert "on_off" in obs.capabilities
        assert "occupancy" in obs.channels


# =============================================================================
# C. dispatch → publish/POST pin (happy-path)
# =============================================================================


class TestDispatchHa:
    """_dispatch_ha: verify the exact POST URL / JSON body sent to HA bridge."""

    HA_URL = "http://ha-bridge:8000"

    def _dispatcher_with_lookup(self, vendor_ref="light.living_room", caps=None):
        caps = caps or ["on_off", "brightness", "color_temp", "color_xy", "color_hs"]
        disp, session, _mqtt = _make_dispatcher(ha_url=self.HA_URL)
        disp.lookup = AsyncMock(
            return_value={
                "device_id": f"ha.{vendor_ref}",
                "vendor": "ha",
                "vendor_ref": vendor_ref,
                "capabilities": caps,
            }
        )
        session.post = MagicMock(return_value=_ok_response({}))
        return disp, session

    @pytest.mark.asyncio
    async def test_on_posts_turn_on(self):
        disp, session = self._dispatcher_with_lookup("light.living_room")
        result = await disp.dispatch("ha.light.living_room", "on")
        assert result["success"] is True
        _, kwargs = session.post.call_args
        body = kwargs["json"]
        assert body["entity_id"] == "light.living_room"
        assert body["service"] == "light/turn_on"
        assert body["data"] == {}

    @pytest.mark.asyncio
    async def test_off_posts_turn_off(self):
        disp, session = self._dispatcher_with_lookup("light.living_room")
        result = await disp.dispatch("ha.light.living_room", "off")
        assert result["success"] is True
        body = session.post.call_args[1]["json"]
        assert body["service"] == "light/turn_off"

    @pytest.mark.asyncio
    async def test_toggle(self):
        disp, session = self._dispatcher_with_lookup("switch.fan", caps=["on_off", "pulse"])
        disp.lookup = AsyncMock(
            return_value={
                "device_id": "ha.switch.fan",
                "vendor": "ha",
                "vendor_ref": "switch.fan",
                "capabilities": ["on_off", "pulse"],
            }
        )
        result = await disp.dispatch("ha.switch.fan", "toggle")
        assert result["success"] is True
        body = session.post.call_args[1]["json"]
        assert body["service"] == "switch/toggle"

    @pytest.mark.asyncio
    async def test_set_brightness(self):
        disp, session = self._dispatcher_with_lookup("light.living_room")
        result = await disp.dispatch("ha.light.living_room", "set_brightness", {"value": 200})
        assert result["success"] is True
        body = session.post.call_args[1]["json"]
        assert body["service"] == "light/turn_on"
        assert body["data"] == {"brightness": 200}

    @pytest.mark.asyncio
    async def test_set_color_temp(self):
        disp, session = self._dispatcher_with_lookup("light.living_room")
        await disp.dispatch("ha.light.living_room", "set_color_temp", {"value": 400})
        body = session.post.call_args[1]["json"]
        assert body["service"] == "light/turn_on"
        assert body["data"] == {"color_temp": 400}

    @pytest.mark.asyncio
    async def test_set_color_xy(self):
        disp, session = self._dispatcher_with_lookup("light.living_room")
        await disp.dispatch("ha.light.living_room", "set_color_xy", {"x": 0.25, "y": 0.35})
        body = session.post.call_args[1]["json"]
        assert body["service"] == "light/turn_on"
        assert body["data"] == {"xy_color": [0.25, 0.35]}

    @pytest.mark.asyncio
    async def test_set_color_hs(self):
        disp, session = self._dispatcher_with_lookup("light.living_room")
        await disp.dispatch("ha.light.living_room", "set_color_hs", {"hue": 180.0, "saturation": 90.0})
        body = session.post.call_args[1]["json"]
        assert body["service"] == "light/turn_on"
        assert body["data"] == {"hs_color": [180.0, 90.0]}

    @pytest.mark.asyncio
    async def test_set_position_cover(self):
        disp, session = self._dispatcher_with_lookup("cover.blinds", caps=["set_position"])
        disp.lookup = AsyncMock(
            return_value={
                "device_id": "ha.cover.blinds",
                "vendor": "ha",
                "vendor_ref": "cover.blinds",
                "capabilities": ["set_position"],
            }
        )
        await disp.dispatch("ha.cover.blinds", "set_position", {"value": 50})
        body = session.post.call_args[1]["json"]
        assert body["service"] == "cover/set_cover_position"
        assert body["data"] == {"position": 50}

    @pytest.mark.asyncio
    async def test_set_temperature_climate(self):
        disp, session = self._dispatcher_with_lookup("climate.aircon", caps=["set_temperature"])
        disp.lookup = AsyncMock(
            return_value={
                "device_id": "ha.climate.aircon",
                "vendor": "ha",
                "vendor_ref": "climate.aircon",
                "capabilities": ["set_temperature"],
            }
        )
        await disp.dispatch("ha.climate.aircon", "set_temperature", {"value": 26.0})
        body = session.post.call_args[1]["json"]
        assert body["service"] == "climate/set_temperature"
        assert body["data"] == {"temperature": 26.0}

    @pytest.mark.asyncio
    async def test_post_url(self):
        """The POST hits exactly HA_BRIDGE_URL/api/device/control."""
        disp, session = self._dispatcher_with_lookup()
        await disp.dispatch("ha.light.living_room", "on")
        url = session.post.call_args[0][0]
        assert url == f"{self.HA_URL}/api/device/control"

    @pytest.mark.asyncio
    async def test_bridge_not_configured_returns_error(self):
        disp, _session = self._dispatcher_with_lookup()
        import device_dispatcher as dd

        dd.HA_BRIDGE_URL = ""
        result = await disp._dispatch_ha({"vendor_ref": "light.x", "device_id": "ha.light.x"}, "on", {})
        assert result["success"] is False
        assert "not configured" in result["error"]


class TestDispatchSwitchbot:
    """_dispatch_switchbot: verify POST URL and body (command/parameter/command_type)."""

    SB_URL = "http://switchbot-bridge:8000"

    def _dispatcher_with_lookup(self, vendor_ref="ABC-123", caps=None):
        caps = caps or ["on_off", "pulse", "brightness", "color_temp", "set_position", "ir_send"]
        disp, session, _mqtt = _make_dispatcher(switchbot_url=self.SB_URL)
        disp.lookup = AsyncMock(
            return_value={
                "device_id": f"switchbot.{vendor_ref}",
                "vendor": "switchbot",
                "vendor_ref": vendor_ref,
                "capabilities": caps,
            }
        )
        session.post = MagicMock(return_value=_ok_response({}))
        return disp, session

    @pytest.mark.asyncio
    async def test_on_command(self):
        disp, session = self._dispatcher_with_lookup()
        result = await disp.dispatch("switchbot.ABC-123", "on")
        assert result["success"] is True
        body = session.post.call_args[1]["json"]
        assert body == {"command": "turnOn", "parameter": "default", "command_type": "command"}

    @pytest.mark.asyncio
    async def test_off_command(self):
        disp, session = self._dispatcher_with_lookup()
        await disp.dispatch("switchbot.ABC-123", "off")
        body = session.post.call_args[1]["json"]
        assert body == {"command": "turnOff", "parameter": "default", "command_type": "command"}

    @pytest.mark.asyncio
    async def test_toggle_command(self):
        disp, session = self._dispatcher_with_lookup()
        await disp.dispatch("switchbot.ABC-123", "toggle")
        body = session.post.call_args[1]["json"]
        assert body == {"command": "toggle", "parameter": "default", "command_type": "command"}

    @pytest.mark.asyncio
    async def test_set_brightness(self):
        disp, session = self._dispatcher_with_lookup()
        await disp.dispatch("switchbot.ABC-123", "set_brightness", {"value": 75})
        body = session.post.call_args[1]["json"]
        assert body == {"command": "setBrightness", "parameter": "75", "command_type": "command"}

    @pytest.mark.asyncio
    async def test_set_color_temp(self):
        disp, session = self._dispatcher_with_lookup()
        await disp.dispatch("switchbot.ABC-123", "set_color_temp", {"value": 4000})
        body = session.post.call_args[1]["json"]
        assert body == {"command": "setColorTemperature", "parameter": "4000", "command_type": "command"}

    @pytest.mark.asyncio
    async def test_set_position(self):
        disp, session = self._dispatcher_with_lookup()
        await disp.dispatch("switchbot.ABC-123", "set_position", {"value": 30})
        body = session.post.call_args[1]["json"]
        assert body == {"command": "setPosition", "parameter": "0,ff,30", "command_type": "command"}

    @pytest.mark.asyncio
    async def test_ir_send(self):
        disp, session = self._dispatcher_with_lookup()
        await disp.dispatch("switchbot.ABC-123", "ir_send", {"command": "myCode", "parameter": "custom_param"})
        body = session.post.call_args[1]["json"]
        assert body == {"command": "myCode", "parameter": "custom_param", "command_type": "customize"}

    @pytest.mark.asyncio
    async def test_post_url_contains_vendor_ref(self):
        disp, session = self._dispatcher_with_lookup("MY-DEVICE-99")
        disp.lookup = AsyncMock(
            return_value={
                "device_id": "switchbot.MY-DEVICE-99",
                "vendor": "switchbot",
                "vendor_ref": "MY-DEVICE-99",
                "capabilities": ["on_off"],
            }
        )
        await disp.dispatch("switchbot.MY-DEVICE-99", "on")
        url = session.post.call_args[0][0]
        assert url == f"{self.SB_URL}/api/devices/MY-DEVICE-99/command"

    @pytest.mark.asyncio
    async def test_bridge_not_configured_returns_error(self):
        disp, _session, _ = _make_dispatcher()
        import device_dispatcher as dd

        dd.SWITCHBOT_BRIDGE_URL = ""
        result = await disp._dispatch_switchbot({"vendor_ref": "ABC-123", "device_id": "switchbot.ABC-123"}, "on", {})
        assert result["success"] is False
        assert "not configured" in result["error"]


class TestDispatchTapo:
    """_dispatch_tapo: verify POST URL/body for on/off/toggle; pulse 2-step."""

    TAPO_URL = "http://tapo-bridge:8000"

    def _dispatcher_with_lookup(self, vendor_ref="192.168.1.100", caps=None):
        caps = caps or ["on_off", "pulse"]
        disp, session, _mqtt = _make_dispatcher(tapo_url=self.TAPO_URL)
        disp.lookup = AsyncMock(
            return_value={
                "device_id": f"tapo.{vendor_ref}",
                "vendor": "tapo",
                "vendor_ref": vendor_ref,
                "capabilities": caps,
            }
        )
        session.post = MagicMock(return_value=_ok_response({}))
        return disp, session

    @pytest.mark.asyncio
    async def test_on_command(self):
        disp, session = self._dispatcher_with_lookup()
        result = await disp.dispatch("tapo.192.168.1.100", "on")
        assert result["success"] is True
        body = session.post.call_args[1]["json"]
        assert body == {"command": "turnOn"}

    @pytest.mark.asyncio
    async def test_off_command(self):
        disp, session = self._dispatcher_with_lookup()
        await disp.dispatch("tapo.192.168.1.100", "off")
        body = session.post.call_args[1]["json"]
        assert body == {"command": "turnOff"}

    @pytest.mark.asyncio
    async def test_toggle_command(self):
        disp, session = self._dispatcher_with_lookup()
        await disp.dispatch("tapo.192.168.1.100", "toggle")
        body = session.post.call_args[1]["json"]
        assert body == {"command": "toggle"}

    @pytest.mark.asyncio
    async def test_post_url_contains_vendor_ref(self):
        disp, session = self._dispatcher_with_lookup("10.0.0.5")
        disp.lookup = AsyncMock(
            return_value={
                "device_id": "tapo.10.0.0.5",
                "vendor": "tapo",
                "vendor_ref": "10.0.0.5",
                "capabilities": ["on_off"],
            }
        )
        await disp.dispatch("tapo.10.0.0.5", "on")
        url = session.post.call_args[0][0]
        assert url == f"{self.TAPO_URL}/api/devices/10.0.0.5/command"

    @pytest.mark.asyncio
    async def test_bridge_not_configured_returns_error(self):
        disp, _, _ = _make_dispatcher()
        import device_dispatcher as dd

        dd.TAPO_BRIDGE_URL = ""
        result = await disp._dispatch_tapo({"vendor_ref": "192.168.1.100", "device_id": "tapo.192.168.1.100"}, "on", {})
        assert result["success"] is False
        assert "not configured" in result["error"]


class TestDispatchZigbee:
    """_dispatch_zigbee: verify MQTT topic and JSON payload per action."""

    def _dispatcher(self, vendor_ref="living_room_bulb", caps=None):
        caps = caps or ["on_off", "brightness", "color_temp", "color_xy", "color_hs", "set_position", "pulse"]
        mqtt = MagicMock()
        disp, _session, _ = _make_dispatcher(mqtt_client=mqtt)
        disp.lookup = AsyncMock(
            return_value={
                "device_id": f"zigbee.{vendor_ref}",
                "vendor": "zigbee",
                "vendor_ref": vendor_ref,
                "capabilities": caps,
            }
        )
        return disp, mqtt

    def _dispatch(self, disp, vendor_ref, action, params=None):
        device = {
            "vendor_ref": vendor_ref,
            "device_id": f"zigbee.{vendor_ref}",
            "capabilities": ["on_off", "brightness", "color_temp", "color_xy", "color_hs", "pulse"],
        }
        return disp._dispatch_zigbee(device, action, params or {})

    def _topic(self, vendor_ref):
        return f"zigbee2mqtt/{vendor_ref}/set"

    def _published_payload(self, mqtt):
        raw = mqtt.publish.call_args[0][1]
        return json.loads(raw)

    def test_on_publishes_state_on(self):
        disp, mqtt = self._dispatcher()
        result = self._dispatch(disp, "living_room_bulb", "on")
        assert result["success"] is True
        mqtt.publish.assert_called_once_with(self._topic("living_room_bulb"), json.dumps({"state": "ON"}))

    def test_off_publishes_state_off(self):
        disp, mqtt = self._dispatcher()
        self._dispatch(disp, "living_room_bulb", "off")
        payload = self._published_payload(mqtt)
        assert payload == {"state": "OFF"}

    def test_toggle_publishes_state_toggle(self):
        disp, mqtt = self._dispatcher()
        self._dispatch(disp, "living_room_bulb", "toggle")
        payload = self._published_payload(mqtt)
        assert payload == {"state": "TOGGLE"}

    def test_set_brightness(self):
        disp, mqtt = self._dispatcher()
        self._dispatch(disp, "living_room_bulb", "set_brightness", {"value": 128})
        payload = self._published_payload(mqtt)
        assert payload == {"state": "ON", "brightness": 128}

    def test_set_color_temp(self):
        disp, mqtt = self._dispatcher()
        self._dispatch(disp, "living_room_bulb", "set_color_temp", {"value": 370})
        payload = self._published_payload(mqtt)
        assert payload == {"color_temp": 370}

    def test_set_color_xy(self):
        disp, mqtt = self._dispatcher()
        self._dispatch(disp, "living_room_bulb", "set_color_xy", {"x": 0.25, "y": 0.35})
        payload = self._published_payload(mqtt)
        assert payload == {"color": {"x": 0.25, "y": 0.35}}

    def test_set_color_hs(self):
        disp, mqtt = self._dispatcher()
        self._dispatch(disp, "living_room_bulb", "set_color_hs", {"hue": 240.0, "saturation": 100.0})
        payload = self._published_payload(mqtt)
        assert payload == {"color": {"hue": 240.0, "saturation": 100.0}}

    def test_topic_format(self):
        """Topic must be exactly zigbee2mqtt/{vendor_ref}/set."""
        disp, mqtt = self._dispatcher("0x00124b0025ad1234")
        self._dispatch(disp, "0x00124b0025ad1234", "on")
        topic = mqtt.publish.call_args[0][0]
        assert topic == "zigbee2mqtt/0x00124b0025ad1234/set"

    def test_mqtt_none_returns_error(self):
        disp, _, _ = _make_dispatcher(mqtt_client=None)
        # DeviceDispatcher stores None mqtt_client when explicitly passed
        disp.mqtt_client = None
        device = {"vendor_ref": "bulb", "device_id": "zigbee.bulb"}
        result = disp._dispatch_zigbee(device, "on", {})
        assert result["success"] is False
        assert "MQTT" in result["error"]


# =============================================================================
# D. Action / capability guard
# =============================================================================


class TestActionCapabilityGuard:
    def _dispatcher(self, caps=None):
        caps = caps or []
        disp, session, _mqtt = _make_dispatcher(ha_url="http://ha:8000")
        disp.lookup = AsyncMock(
            return_value={
                "device_id": "ha.light.x",
                "vendor": "ha",
                "vendor_ref": "light.x",
                "capabilities": caps,
            }
        )
        session.post = MagicMock(return_value=_ok_response({}))
        return disp

    @pytest.mark.asyncio
    async def test_unknown_action_rejected(self):
        disp = self._dispatcher(["on_off"])
        result = await disp.dispatch("ha.light.x", "explode")
        assert result["success"] is False
        assert "Unknown action" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_capability_rejected(self):
        disp = self._dispatcher(["on_off"])  # no brightness cap
        result = await disp.dispatch("ha.light.x", "set_brightness", {"value": 100})
        assert result["success"] is False
        assert "brightness" in result["error"]

    @pytest.mark.asyncio
    async def test_present_capability_passes(self):
        disp = self._dispatcher(["on_off", "brightness"])
        result = await disp.dispatch("ha.light.x", "set_brightness", {"value": 100})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_device_not_registered_returns_error(self):
        disp, _session, _ = _make_dispatcher(ha_url="http://ha:8000")
        disp.lookup = AsyncMock(return_value=None)
        result = await disp.dispatch("ha.light.nonexistent", "on")
        assert result["success"] is False
        assert "not registered" in result["error"]

    @pytest.mark.asyncio
    async def test_mcp_vendor_returns_error(self):
        disp, _session, _ = _make_dispatcher()
        disp.lookup = AsyncMock(
            return_value={
                "device_id": "mcp.sensor_01",
                "vendor": "mcp",
                "vendor_ref": "sensor_01",
                "capabilities": ["on_off"],
            }
        )
        result = await disp.dispatch("mcp.sensor_01", "on")
        assert result["success"] is False
        assert "send_device_command" in result["error"]


# =============================================================================
# E. Error formatting — _tapo_raw exception→error, bridge 4xx detail extraction
# =============================================================================


class TestErrorFormatting:
    TAPO_URL = "http://tapo-bridge:8000"
    HA_URL = "http://ha-bridge:8000"
    SB_URL = "http://sb-bridge:8000"

    @pytest.mark.asyncio
    async def test_tapo_raw_exception_becomes_error_string(self):
        """_tapo_raw must catch exceptions and return error string (not raise)."""
        import device_dispatcher as dd

        dd.TAPO_BRIDGE_URL = self.TAPO_URL

        import aiohttp

        session = MagicMock(spec=aiohttp.ClientSession)

        # Make session.post raise a network error
        err_resp = AsyncMock()
        err_resp.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("timeout"))
        err_resp.__aexit__ = AsyncMock(return_value=False)
        session.post = MagicMock(return_value=err_resp)

        from device_dispatcher import DeviceDispatcher

        disp = DeviceDispatcher(session=session, mqtt_client=None)
        result = await disp._tapo_raw("192.168.1.100", "turnOn")
        assert result["success"] is False
        assert isinstance(result["error"], str)
        assert len(result["error"]) > 0

    @pytest.mark.asyncio
    async def test_ha_bridge_4xx_extracts_detail(self):
        """A 4xx response with JSON detail field is surfaced in the error."""
        import device_dispatcher as dd

        dd.HA_BRIDGE_URL = self.HA_URL

        import aiohttp

        session = MagicMock(spec=aiohttp.ClientSession)
        session.post = MagicMock(return_value=_err_response(status=404, detail="entity not found"))

        from device_dispatcher import DeviceDispatcher

        disp = DeviceDispatcher(session=session, mqtt_client=None)
        result = await disp._dispatch_ha({"vendor_ref": "light.x", "device_id": "ha.light.x"}, "on", {})
        assert result["success"] is False
        assert "entity not found" in result["error"]

    @pytest.mark.asyncio
    async def test_ha_bridge_4xx_no_detail_falls_back_to_http_status(self):
        import device_dispatcher as dd

        dd.HA_BRIDGE_URL = self.HA_URL

        import aiohttp

        session = MagicMock(spec=aiohttp.ClientSession)
        # No 'detail' key in the response JSON
        resp = AsyncMock()
        resp.status = 503
        resp.json = AsyncMock(return_value={"message": "unavailable"})
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session.post = MagicMock(return_value=resp)

        from device_dispatcher import DeviceDispatcher

        disp = DeviceDispatcher(session=session, mqtt_client=None)
        result = await disp._dispatch_ha({"vendor_ref": "light.x", "device_id": "ha.light.x"}, "on", {})
        assert result["success"] is False
        assert "HTTP 503" in result["error"]

    @pytest.mark.asyncio
    async def test_switchbot_bridge_4xx_detail_extracted(self):
        import device_dispatcher as dd

        dd.SWITCHBOT_BRIDGE_URL = self.SB_URL

        import aiohttp

        session = MagicMock(spec=aiohttp.ClientSession)
        session.post = MagicMock(return_value=_err_response(status=422, detail="device offline"))

        from device_dispatcher import DeviceDispatcher

        disp = DeviceDispatcher(session=session, mqtt_client=None)
        result = await disp._dispatch_switchbot({"vendor_ref": "ABC-123", "device_id": "switchbot.ABC-123"}, "on", {})
        assert result["success"] is False
        assert "device offline" in result["error"]


# =============================================================================
# F. Special mechanisms: pulse / rainbow / zigbee_permit_join
# =============================================================================


class TestTapoPulse:
    """Tapo pulse = on → asyncio.sleep(duration) → off, 2 POSTs in order."""

    TAPO_URL = "http://tapo-bridge:8000"

    @pytest.mark.asyncio
    async def test_pulse_sends_on_then_off(self):
        import device_dispatcher as dd

        dd.TAPO_BRIDGE_URL = self.TAPO_URL

        import aiohttp

        session = MagicMock(spec=aiohttp.ClientSession)
        # Each call returns success
        session.post = MagicMock(return_value=_ok_response({}))

        from device_dispatcher import DeviceDispatcher

        disp = DeviceDispatcher(session=session, mqtt_client=None)
        device = {"vendor_ref": "192.168.1.100", "device_id": "tapo.192.168.1.100"}

        with patch("device_dispatcher.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await disp._dispatch_tapo(device, "pulse", {"duration_s": 5})

        assert result["success"] is True
        assert "pulse" in result["result"]
        # Should have made exactly 2 POSTs: turnOn then turnOff
        assert session.post.call_count == 2
        first_body = session.post.call_args_list[0][1]["json"]
        second_body = session.post.call_args_list[1][1]["json"]
        assert first_body == {"command": "turnOn"}
        assert second_body == {"command": "turnOff"}
        # Sleep was called with the duration
        mock_sleep.assert_awaited_once_with(5)

    @pytest.mark.asyncio
    async def test_pulse_duration_too_large_rejected(self):
        import device_dispatcher as dd

        dd.TAPO_BRIDGE_URL = self.TAPO_URL

        import aiohttp

        session = MagicMock(spec=aiohttp.ClientSession)
        from device_dispatcher import DeviceDispatcher

        disp = DeviceDispatcher(session=session, mqtt_client=None)
        device = {"vendor_ref": "192.168.1.100", "device_id": "tapo.192.168.1.100"}
        result = await disp._dispatch_tapo(device, "pulse", {"duration_s": 601})
        assert result["success"] is False
        assert "600" in result["error"]

    @pytest.mark.asyncio
    async def test_pulse_on_failure_aborts_off(self):
        """If turnOn fails, off should NOT be attempted."""
        import device_dispatcher as dd

        dd.TAPO_BRIDGE_URL = self.TAPO_URL

        import aiohttp

        session = MagicMock(spec=aiohttp.ClientSession)
        session.post = MagicMock(return_value=_err_response(status=503, detail="network error"))

        from device_dispatcher import DeviceDispatcher

        disp = DeviceDispatcher(session=session, mqtt_client=None)
        device = {"vendor_ref": "192.168.1.100", "device_id": "tapo.192.168.1.100"}

        with patch("device_dispatcher.asyncio.sleep", new_callable=AsyncMock):
            result = await disp._dispatch_tapo(device, "pulse", {"duration_s": 5})

        assert result["success"] is False
        # Only 1 POST (the failed turnOn), no second POST for turnOff
        assert session.post.call_count == 1


class TestZigbeePulse:
    """Zigbee pulse = publish ON + loop.call_later(duration, publish OFF).

    _dispatch_zigbee is synchronous but calls asyncio.get_running_loop() internally,
    so tests run it inside an async context to satisfy that requirement.
    """

    def _dispatcher(self, vendor_ref="outlet_01"):
        mqtt = MagicMock()
        disp, _, _ = _make_dispatcher(mqtt_client=mqtt)
        return disp, mqtt

    @pytest.mark.asyncio
    async def test_pulse_publishes_on_immediately(self):
        disp, mqtt = self._dispatcher()
        result = disp._dispatch_zigbee(
            {"vendor_ref": "outlet_01", "device_id": "zigbee.outlet_01", "capabilities": ["on_off", "pulse"]},
            "pulse",
            {"duration_s": 10},
        )
        assert result["success"] is True
        # The first (and only immediate) publish is ON
        first_call = mqtt.publish.call_args_list[0]
        assert first_call[0][0] == "zigbee2mqtt/outlet_01/set"
        assert json.loads(first_call[0][1]) == {"state": "ON"}

    @pytest.mark.asyncio
    async def test_pulse_schedules_off_via_call_later(self):
        """call_later is used for the deferred OFF; verify delay and that it is scheduled."""
        disp, _mqtt = self._dispatcher()
        loop = asyncio.get_event_loop()
        call_later_calls: list = []
        original_cl = loop.call_later

        def capturing_cl(delay, callback, *args):
            call_later_calls.append((delay, callback))
            return original_cl(delay, callback, *args)

        loop.call_later = capturing_cl
        try:
            result = disp._dispatch_zigbee(
                {"vendor_ref": "outlet_01", "device_id": "zigbee.outlet_01", "capabilities": ["on_off", "pulse"]},
                "pulse",
                {"duration_s": 30},
            )
        finally:
            loop.call_later = original_cl

        assert result["success"] is True
        assert len(call_later_calls) == 1
        delay, _ = call_later_calls[0]
        assert delay == 30

    @pytest.mark.asyncio
    async def test_pulse_duration_too_large_rejected(self):
        disp, _ = self._dispatcher()
        result = disp._dispatch_zigbee(
            {"vendor_ref": "outlet_01", "device_id": "zigbee.outlet_01", "capabilities": ["on_off", "pulse"]},
            "pulse",
            {"duration_s": 601},
        )
        assert result["success"] is False
        assert "600" in result["error"]


class TestZigbeeRainbow:
    """Zigbee rainbow = publish ON+brightness + N call_later hue steps + warm-white restore.

    _dispatch_zigbee is synchronous but calls asyncio.get_running_loop() internally,
    so tests run inside an async context.
    """

    @pytest.mark.asyncio
    async def test_rainbow_initial_publish_on_brightness(self):
        mqtt = MagicMock()
        disp, _, _ = _make_dispatcher(mqtt_client=mqtt)
        device = {
            "vendor_ref": "ceiling_rgb",
            "device_id": "zigbee.ceiling_rgb",
            "capabilities": ["on_off", "brightness", "color_hs"],
        }
        result = disp._dispatch_zigbee(device, "rainbow", {"duration_s": 10})
        assert result["success"] is True
        # First publish: ON + full brightness
        first_publish_payload = json.loads(mqtt.publish.call_args_list[0][0][1])
        assert first_publish_payload == {"state": "ON", "brightness": 254}

    @pytest.mark.asyncio
    async def test_rainbow_steps_and_restore_call_later_count(self):
        """duration=10 → steps=min(10*2,20)=20 steps + 1 restore = 21 call_later calls."""
        mqtt = MagicMock()
        disp, _, _ = _make_dispatcher(mqtt_client=mqtt)
        device = {
            "vendor_ref": "ceiling_rgb",
            "device_id": "zigbee.ceiling_rgb",
            "capabilities": ["on_off", "brightness", "color_hs"],
        }
        loop = asyncio.get_event_loop()
        call_later_calls: list = []
        original_cl = loop.call_later

        def capturing_cl(delay, callback, *args):
            call_later_calls.append((delay, callback))
            return original_cl(delay, callback, *args)

        loop.call_later = capturing_cl
        try:
            result = disp._dispatch_zigbee(device, "rainbow", {"duration_s": 10})
        finally:
            loop.call_later = original_cl

        assert result["success"] is True
        # 20 hue steps + 1 warm-white restore = 21
        assert len(call_later_calls) == 21

    @pytest.mark.asyncio
    async def test_rainbow_steps_capped_at_20_for_short_duration(self):
        """duration=4 → steps=min(4*2,20)=8 steps + 1 restore = 9 call_later calls."""
        mqtt = MagicMock()
        disp, _, _ = _make_dispatcher(mqtt_client=mqtt)
        device = {
            "vendor_ref": "rgb_bulb",
            "device_id": "zigbee.rgb_bulb",
            "capabilities": ["on_off", "brightness", "color_hs"],
        }
        loop = asyncio.get_event_loop()
        call_later_calls: list = []
        original_cl = loop.call_later

        def capturing_cl(delay, callback, *args):
            call_later_calls.append((delay, callback))
            return original_cl(delay, callback, *args)

        loop.call_later = capturing_cl
        try:
            disp._dispatch_zigbee(device, "rainbow", {"duration_s": 4})
        finally:
            loop.call_later = original_cl

        assert len(call_later_calls) == 9  # 8 hue + 1 restore

    @pytest.mark.asyncio
    async def test_rainbow_duration_too_large_rejected(self):
        mqtt = MagicMock()
        disp, _, _ = _make_dispatcher(mqtt_client=mqtt)
        device = {
            "vendor_ref": "rgb_bulb",
            "device_id": "zigbee.rgb_bulb",
            "capabilities": ["on_off", "brightness", "color_hs"],
        }
        result = disp._dispatch_zigbee(device, "rainbow", {"duration_s": 61})
        assert result["success"] is False
        assert "60" in result["error"]

    @pytest.mark.asyncio
    async def test_rainbow_warm_white_restore_delay(self):
        """The warm-white call_later is scheduled at duration + 0.5."""
        mqtt = MagicMock()
        disp, _, _ = _make_dispatcher(mqtt_client=mqtt)
        device = {
            "vendor_ref": "ceiling_rgb",
            "device_id": "zigbee.ceiling_rgb",
            "capabilities": ["on_off", "brightness", "color_hs"],
        }
        loop = asyncio.get_event_loop()
        call_later_calls: list = []
        original_cl = loop.call_later

        def capturing_cl(delay, callback, *args):
            call_later_calls.append((delay, callback))
            return original_cl(delay, callback, *args)

        loop.call_later = capturing_cl
        try:
            disp._dispatch_zigbee(device, "rainbow", {"duration_s": 10})
        finally:
            loop.call_later = original_cl

        # Last call_later is the warm-white restore at duration + 0.5
        last_delay, _last_callback = call_later_calls[-1]
        assert last_delay == pytest.approx(10.5)


class TestHaRainbow:
    """HA rainbow: asyncio.ensure_future schedules _ha_rainbow; return is immediate."""

    HA_URL = "http://ha-bridge:8000"

    @pytest.mark.asyncio
    async def test_rainbow_returns_immediately_without_waiting(self):
        import device_dispatcher as dd

        dd.HA_BRIDGE_URL = self.HA_URL

        import aiohttp

        session = MagicMock(spec=aiohttp.ClientSession)
        session.post = MagicMock(return_value=_ok_response({}))

        from device_dispatcher import DeviceDispatcher

        disp = DeviceDispatcher(session=session, mqtt_client=None)
        device = {
            "vendor_ref": "light.ceiling",
            "device_id": "ha.light.ceiling",
            "capabilities": ["on_off", "brightness", "color_hs"],
        }

        # Patch ensure_future to prevent it from actually running
        with patch("device_dispatcher.asyncio.ensure_future") as mock_ef:
            result = await disp._dispatch_ha(device, "rainbow", {"duration_s": 5})

        assert result["success"] is True
        assert "rainbow" in result["result"]
        mock_ef.assert_called_once()

    @pytest.mark.asyncio
    async def test_rainbow_duration_too_large_rejected(self):
        import device_dispatcher as dd

        dd.HA_BRIDGE_URL = self.HA_URL

        import aiohttp

        session = MagicMock(spec=aiohttp.ClientSession)
        from device_dispatcher import DeviceDispatcher

        disp = DeviceDispatcher(session=session, mqtt_client=None)
        device = {
            "vendor_ref": "light.ceiling",
            "device_id": "ha.light.ceiling",
            "capabilities": ["on_off", "brightness", "color_hs"],
        }
        # duration > 60 is rejected before asyncio.ensure_future is called,
        # so no coroutine is ever created here.
        result = await disp._dispatch_ha(device, "rainbow", {"duration_s": 61})
        assert result["success"] is False
        assert "60" in result["error"]

    @pytest.mark.asyncio
    async def test_ha_rainbow_hue_step_count(self):
        """_ha_rainbow with duration=10: steps=min(10*2,20)=20 → 20 hue POSTs + 1 restore."""
        import device_dispatcher as dd

        dd.HA_BRIDGE_URL = self.HA_URL

        import aiohttp

        session = MagicMock(spec=aiohttp.ClientSession)
        session.post = MagicMock(return_value=_ok_response({}))

        from device_dispatcher import DeviceDispatcher

        disp = DeviceDispatcher(session=session, mqtt_client=None)

        with patch("device_dispatcher.asyncio.sleep", new_callable=AsyncMock):
            await disp._ha_rainbow("light.ceiling", duration=10)

        # 20 hue steps + 1 warm-white restore = 21
        assert session.post.call_count == 21

    @pytest.mark.asyncio
    async def test_ha_rainbow_last_call_is_warm_white(self):
        """The last POST must be color_temp=350 (warm white restore)."""
        import device_dispatcher as dd

        dd.HA_BRIDGE_URL = self.HA_URL

        import aiohttp

        session = MagicMock(spec=aiohttp.ClientSession)
        session.post = MagicMock(return_value=_ok_response({}))

        from device_dispatcher import DeviceDispatcher

        disp = DeviceDispatcher(session=session, mqtt_client=None)

        with patch("device_dispatcher.asyncio.sleep", new_callable=AsyncMock):
            await disp._ha_rainbow("light.ceiling", duration=10)

        last_body = session.post.call_args_list[-1][1]["json"]
        assert last_body == {
            "entity_id": "light.ceiling",
            "service": "light/turn_on",
            "data": {"color_temp": 350},
        }


class TestZigbeePermitJoin:
    """zigbee_permit_join: verify the MQTT publish to bridge/request/permit_join."""

    def _dispatcher(self):
        mqtt = MagicMock()
        disp, _, _ = _make_dispatcher(mqtt_client=mqtt)
        return disp, mqtt

    def test_enable_no_duration(self):
        disp, mqtt = self._dispatcher()
        result = disp.zigbee_permit_join(enable=True)
        assert result["success"] is True
        mqtt.publish.assert_called_once()
        topic = mqtt.publish.call_args[0][0]
        payload = json.loads(mqtt.publish.call_args[0][1])
        assert topic == "zigbee2mqtt/bridge/request/permit_join"
        assert payload == {"value": True}

    def test_enable_with_duration(self):
        disp, mqtt = self._dispatcher()
        result = disp.zigbee_permit_join(enable=True, duration_s=120)
        assert result["success"] is True
        payload = json.loads(mqtt.publish.call_args[0][1])
        assert payload == {"value": True, "time": 120}

    def test_disable(self):
        disp, mqtt = self._dispatcher()
        result = disp.zigbee_permit_join(enable=False)
        assert result["success"] is True
        payload = json.loads(mqtt.publish.call_args[0][1])
        assert payload == {"value": False}

    def test_invalid_duration_rejected(self):
        disp, mqtt = self._dispatcher()
        result = disp.zigbee_permit_join(enable=True, duration_s=9999)
        assert result["success"] is False
        mqtt.publish.assert_not_called()

    def test_negative_duration_rejected(self):
        disp, mqtt = self._dispatcher()
        result = disp.zigbee_permit_join(enable=True, duration_s=-1)
        assert result["success"] is False
        mqtt.publish.assert_not_called()

    def test_no_mqtt_client_returns_error(self):
        disp, _, _ = _make_dispatcher(mqtt_client=None)
        disp.mqtt_client = None
        result = disp.zigbee_permit_join(enable=True)
        assert result["success"] is False


# =============================================================================
# G. ALLOWED_ACTIONS and _ha_service_for / _switchbot_cmd_for / _zigbee_payload_for
#    (pure-function pin — no I/O)
# =============================================================================


class TestHaServiceFor:
    def _call(self, action, params=None, domain="light"):
        from device_dispatcher import _ha_service_for

        return _ha_service_for(action, params or {}, domain)

    def test_on(self):
        svc, data = self._call("on")
        assert svc == "light/turn_on"
        assert data == {}

    def test_off(self):
        svc, _data = self._call("off")
        assert svc == "light/turn_off"

    def test_toggle(self):
        svc, _data = self._call("toggle")
        assert svc == "light/toggle"

    def test_set_brightness_default(self):
        svc, data = self._call("set_brightness")
        assert svc == "light/turn_on"
        assert data == {"brightness": 128}

    def test_set_brightness_custom(self):
        _, data = self._call("set_brightness", {"value": 200})
        assert data == {"brightness": 200}

    def test_set_color_temp(self):
        svc, data = self._call("set_color_temp", {"value": 400})
        assert svc == "light/turn_on"
        assert data == {"color_temp": 400}

    def test_set_color_xy_defaults(self):
        svc, data = self._call("set_color_xy")
        assert svc == "light/turn_on"
        assert data == {"xy_color": [0.3, 0.3]}

    def test_set_color_hs_defaults(self):
        svc, data = self._call("set_color_hs")
        assert svc == "light/turn_on"
        assert data == {"hs_color": [0.0, 100.0]}

    def test_set_position(self):
        svc, data = self._call("set_position", {"value": 75}, domain="cover")
        assert svc == "cover/set_cover_position"
        assert data == {"position": 75}

    def test_set_temperature(self):
        svc, data = self._call("set_temperature", {"value": 25.5}, domain="climate")
        assert svc == "climate/set_temperature"
        assert data == {"temperature": 25.5}

    def test_unknown_action_returns_none(self):
        svc, _data = self._call("explode")
        assert svc is None


class TestSwitchbotCmdFor:
    def _call(self, action, params=None):
        from device_dispatcher import _switchbot_cmd_for

        return _switchbot_cmd_for(action, params or {})

    def test_on(self):
        cmd, param, ctype = self._call("on")
        assert (cmd, param, ctype) == ("turnOn", "default", "command")

    def test_off(self):
        assert self._call("off") == ("turnOff", "default", "command")

    def test_toggle(self):
        assert self._call("toggle") == ("toggle", "default", "command")

    def test_set_brightness_default(self):
        cmd, param, ctype = self._call("set_brightness")
        assert cmd == "setBrightness"
        assert param == "50"
        assert ctype == "command"

    def test_set_color_temp(self):
        cmd, param, _ctype = self._call("set_color_temp", {"value": 4500})
        assert cmd == "setColorTemperature"
        assert param == "4500"

    def test_set_position(self):
        cmd, param, _ctype = self._call("set_position", {"value": 40})
        assert cmd == "setPosition"
        assert param == "0,ff,40"

    def test_ir_send_default(self):
        cmd, _param, ctype = self._call("ir_send")
        assert cmd == "turnOn"  # default when no 'command' param
        assert ctype == "customize"

    def test_ir_send_custom(self):
        cmd, param, ctype = self._call("ir_send", {"command": "myCode", "parameter": "p1"})
        assert cmd == "myCode"
        assert param == "p1"
        assert ctype == "customize"

    def test_unknown_action_returns_none_triple(self):
        cmd, param, ctype = self._call("fly")
        assert cmd is None
        assert param == ""
        assert ctype == ""


class TestZigbeePayloadFor:
    def _call(self, action, params=None):
        from device_dispatcher import _zigbee_payload_for

        return _zigbee_payload_for(action, params or {})

    def test_on(self):
        assert self._call("on") == {"state": "ON"}

    def test_off(self):
        assert self._call("off") == {"state": "OFF"}

    def test_toggle(self):
        assert self._call("toggle") == {"state": "TOGGLE"}

    def test_set_brightness_default(self):
        p = self._call("set_brightness")
        assert p == {"state": "ON", "brightness": 128}

    def test_set_brightness_custom(self):
        p = self._call("set_brightness", {"value": 200})
        assert p == {"state": "ON", "brightness": 200}

    def test_set_color_temp(self):
        p = self._call("set_color_temp", {"value": 370})
        assert p == {"color_temp": 370}

    def test_set_color_xy(self):
        p = self._call("set_color_xy", {"x": 0.25, "y": 0.35})
        assert p == {"color": {"x": 0.25, "y": 0.35}}

    def test_set_color_xy_defaults(self):
        p = self._call("set_color_xy")
        assert p == {"color": {"x": 0.3, "y": 0.3}}

    def test_set_color_hs(self):
        p = self._call("set_color_hs", {"hue": 120.0, "saturation": 80.0})
        assert p == {"color": {"hue": 120.0, "saturation": 80.0}}

    def test_pulse_returns_on_payload(self):
        # pulse returns {"state": "ON"} (the actual pulse mechanism is in _dispatch_zigbee)
        p = self._call("pulse")
        assert p == {"state": "ON"}

    def test_unknown_action_returns_none(self):
        assert self._call("fly_to_moon") is None


class TestAllowedActions:
    def test_all_expected_actions_present(self):
        # W3.4-C2: ALLOWED_ACTIONS renamed to DEVICE_ALLOWED_ACTIONS (no alias).
        from device_dispatcher import DEVICE_ALLOWED_ACTIONS

        expected = {
            "on",
            "off",
            "toggle",
            "set_brightness",
            "set_color_temp",
            "set_color_xy",
            "set_color_hs",
            "set_position",
            "set_temperature",
            "pulse",
            "rainbow",
            "ir_send",
        }
        assert expected == DEVICE_ALLOWED_ACTIONS
