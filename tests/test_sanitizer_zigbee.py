"""
Tests for Sanitizer validation of Zigbee-related tools.
"""
import pytest


class TestControlSwitchValidation:
    def test_valid_switch(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "control_switch", {"entity_id": "switch.plug_washer", "on": True},
        )
        assert result["allowed"] is True

    def test_missing_entity_id(self, sanitizer):
        result = sanitizer.validate_tool_call("control_switch", {"on": True})
        assert result["allowed"] is False
        assert "entity_id" in result["reason"]

    def test_empty_entity_id(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "control_switch", {"entity_id": "", "on": True},
        )
        assert result["allowed"] is False

    def test_wrong_prefix(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "control_switch", {"entity_id": "light.living", "on": True},
        )
        assert result["allowed"] is False
        assert "switch." in result["reason"]

    def test_switch_off(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "control_switch", {"entity_id": "switch.plug", "on": False},
        )
        assert result["allowed"] is True


class TestExecuteSceneValidation:
    def test_valid_scene(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "execute_scene", {"entity_id": "scene.good_night"},
        )
        assert result["allowed"] is True

    def test_missing_entity_id(self, sanitizer):
        result = sanitizer.validate_tool_call("execute_scene", {})
        assert result["allowed"] is False
        assert "entity_id" in result["reason"]

    def test_empty_entity_id(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "execute_scene", {"entity_id": ""},
        )
        assert result["allowed"] is False

    def test_wrong_prefix(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "execute_scene", {"entity_id": "switch.plug"},
        )
        assert result["allowed"] is False
        assert "scene." in result["reason"]


class TestGetSensorDataValidation:
    def test_get_sensor_data_allowed(self, sanitizer):
        """get_sensor_data is a read-only tool, always allowed."""
        result = sanitizer.validate_tool_call("get_sensor_data", {})
        assert result["allowed"] is True

    def test_get_sensor_data_with_entity_id(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "get_sensor_data", {"entity_id": "sensor.washer_power"},
        )
        assert result["allowed"] is True

    def test_get_sensor_data_with_device_class(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "get_sensor_data", {"device_class": "power"},
        )
        assert result["allowed"] is True
