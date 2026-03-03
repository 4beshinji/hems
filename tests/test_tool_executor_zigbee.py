"""
Tests for ToolExecutor Zigbee tool handlers.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from world_model.data_classes import (
    BinarySensorState, HASensorState, LightState,
)


class TestControlSwitch:
    @pytest.mark.asyncio
    async def test_switch_on(self, tool_executor, mock_session):
        mock_session.post = MagicMock(return_value=mock_session._make_response(200, {}))
        tool_executor.ha_url = "http://ha-bridge:8000"
        result = await tool_executor.execute(
            "control_switch", {"entity_id": "switch.plug", "on": True},
        )
        assert result["success"] is True
        call_args = mock_session.post.call_args
        body = call_args[1]["json"] if "json" in call_args[1] else call_args.kwargs["json"]
        assert body["service"] == "switch/turn_on"

    @pytest.mark.asyncio
    async def test_switch_off(self, tool_executor, mock_session):
        mock_session.post = MagicMock(return_value=mock_session._make_response(200, {}))
        tool_executor.ha_url = "http://ha-bridge:8000"
        result = await tool_executor.execute(
            "control_switch", {"entity_id": "switch.plug", "on": False},
        )
        assert result["success"] is True
        call_args = mock_session.post.call_args
        body = call_args[1]["json"] if "json" in call_args[1] else call_args.kwargs["json"]
        assert body["service"] == "switch/turn_off"

    @pytest.mark.asyncio
    async def test_switch_no_ha(self, tool_executor):
        tool_executor.ha_url = ""
        result = await tool_executor.execute(
            "control_switch", {"entity_id": "switch.plug", "on": True},
        )
        assert result["success"] is False
        assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_switch_rejected_wrong_prefix(self, tool_executor):
        result = await tool_executor.execute(
            "control_switch", {"entity_id": "light.plug", "on": True},
        )
        assert result["success"] is False


class TestGetSensorData:
    @pytest.mark.asyncio
    async def test_get_all_sensors(self, tool_executor, world_model):
        world_model.home_devices.sensors["sensor.power"] = HASensorState(
            entity_id="sensor.power", value=120, unit="W", device_class="power",
        )
        world_model.home_devices.sensors["sensor.co2"] = HASensorState(
            entity_id="sensor.co2", value=800, unit="ppm", device_class="carbon_dioxide",
        )
        result = await tool_executor.execute("get_sensor_data", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert "sensor.power" in data
        assert "sensor.co2" in data

    @pytest.mark.asyncio
    async def test_get_sensor_by_id(self, tool_executor, world_model):
        world_model.home_devices.sensors["sensor.power"] = HASensorState(
            entity_id="sensor.power", value=120, unit="W", device_class="power",
        )
        result = await tool_executor.execute(
            "get_sensor_data", {"entity_id": "sensor.power"},
        )
        assert result["success"] is True
        data = json.loads(result["result"])
        assert data["value"] == 120
        assert data["unit"] == "W"

    @pytest.mark.asyncio
    async def test_get_sensor_not_found(self, tool_executor, world_model):
        result = await tool_executor.execute(
            "get_sensor_data", {"entity_id": "sensor.nonexistent"},
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_sensors_by_device_class(self, tool_executor, world_model):
        world_model.home_devices.sensors["sensor.power1"] = HASensorState(
            entity_id="sensor.power1", value=100, device_class="power",
        )
        world_model.home_devices.sensors["sensor.power2"] = HASensorState(
            entity_id="sensor.power2", value=200, device_class="power",
        )
        world_model.home_devices.sensors["sensor.co2"] = HASensorState(
            entity_id="sensor.co2", value=800, device_class="carbon_dioxide",
        )
        result = await tool_executor.execute(
            "get_sensor_data", {"device_class": "power"},
        )
        data = json.loads(result["result"])
        assert len(data) == 2
        assert "sensor.power1" in data
        assert "sensor.power2" in data
        assert "sensor.co2" not in data


class TestExecuteScene:
    @pytest.mark.asyncio
    async def test_scene_execution(self, tool_executor, mock_session):
        mock_session.post = MagicMock(return_value=mock_session._make_response(200, {}))
        tool_executor.ha_url = "http://ha-bridge:8000"
        result = await tool_executor.execute(
            "execute_scene", {"entity_id": "scene.good_night"},
        )
        assert result["success"] is True
        call_args = mock_session.post.call_args
        body = call_args[1]["json"] if "json" in call_args[1] else call_args.kwargs["json"]
        assert body["service"] == "scene/turn_on"
        assert body["entity_id"] == "scene.good_night"

    @pytest.mark.asyncio
    async def test_scene_rejected_wrong_prefix(self, tool_executor):
        result = await tool_executor.execute(
            "execute_scene", {"entity_id": "switch.plug"},
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_scene_no_ha(self, tool_executor):
        tool_executor.ha_url = ""
        result = await tool_executor.execute(
            "execute_scene", {"entity_id": "scene.good_night"},
        )
        assert result["success"] is False


class TestGetHomeDevicesExtended:
    """get_home_devices now includes binary_sensors and sensors."""

    @pytest.mark.asyncio
    async def test_includes_binary_sensors(self, tool_executor, world_model):
        world_model.home_devices.binary_sensors["binary_sensor.door"] = BinarySensorState(
            entity_id="binary_sensor.door", state=True, device_class="door",
        )
        result = await tool_executor.execute("get_home_devices", {})
        data = json.loads(result["result"])
        assert "binary_sensors" in data
        assert "binary_sensor.door" in data["binary_sensors"]
        assert data["binary_sensors"]["binary_sensor.door"]["state"] is True
        assert data["binary_sensors"]["binary_sensor.door"]["device_class"] == "door"

    @pytest.mark.asyncio
    async def test_includes_sensors(self, tool_executor, world_model):
        world_model.home_devices.sensors["sensor.power"] = HASensorState(
            entity_id="sensor.power", value=150, unit="W", device_class="power",
        )
        result = await tool_executor.execute("get_home_devices", {})
        data = json.loads(result["result"])
        assert "sensors" in data
        assert "sensor.power" in data["sensors"]
        assert data["sensors"]["sensor.power"]["value"] == 150
        assert data["sensors"]["sensor.power"]["device_class"] == "power"

    @pytest.mark.asyncio
    async def test_still_includes_lights_climates(self, tool_executor, world_model):
        """Existing fields (lights, climates, etc.) are still present."""
        world_model.home_devices.lights["light.a"] = LightState(
            entity_id="light.a", on=True, brightness=200,
        )
        result = await tool_executor.execute("get_home_devices", {})
        data = json.loads(result["result"])
        assert "lights" in data
        assert "light.a" in data["lights"]
        assert "binary_sensors" in data
        assert "sensors" in data
