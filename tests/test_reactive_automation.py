"""Tests for reactive automation immediate motion triggers.

Covers MqttSyncMixin._trigger_motion_event and AutomationEngine wildcard
matching. See project_reactive_automation.md for motivation.
"""

from unittest.mock import MagicMock, patch

import pytest

from brain_mqtt import MqttSyncMixin
from world_model import WorldModel


class _Harness(MqttSyncMixin):
    """Minimal harness for _trigger_motion_event."""

    def __init__(self, world_model: WorldModel):
        self.world_model = world_model
        self.automation_engine = MagicMock()
        self._loop = MagicMock()


@pytest.fixture
def wm():
    return WorldModel()


@pytest.fixture
def harness(wm):
    return _Harness(wm)


@pytest.fixture
def scheduled_coros():
    """Patch asyncio.run_coroutine_threadsafe in brain_mqtt and count calls."""
    with patch("brain_mqtt.asyncio.run_coroutine_threadsafe") as mock:
        yield mock


class TestTriggerMotionEvent:
    def test_zigbee_occupancy_true(self, harness, scheduled_coros):
        harness._trigger_motion_event(
            "zigbee2mqtt/pir_entrance",
            {"occupancy": True, "zone": "entrance"},
            ["zigbee2mqtt", "pir_entrance"],
        )
        harness.automation_engine.trigger_event.assert_called_once_with("motion:pir_entrance")
        scheduled_coros.assert_called_once()
        assert scheduled_coros.call_args[0][1] is harness._loop

    def test_zigbee_motion_true(self, harness, scheduled_coros):
        harness._trigger_motion_event(
            "zigbee2mqtt/motion_living",
            {"motion": True, "zone": "living_room"},
            ["zigbee2mqtt", "motion_living"],
        )
        harness.automation_engine.trigger_event.assert_called_once_with("motion:motion_living")
        scheduled_coros.assert_called_once()

    def test_zigbee_occupancy_false(self, harness, scheduled_coros):
        harness._trigger_motion_event(
            "zigbee2mqtt/pir_entrance",
            {"occupancy": False, "zone": "entrance"},
            ["zigbee2mqtt", "pir_entrance"],
        )
        harness.automation_engine.trigger_event.assert_not_called()
        scheduled_coros.assert_not_called()

    def test_zigbee_bridge_topic_ignored(self, harness, scheduled_coros):
        harness._trigger_motion_event(
            "zigbee2mqtt/bridge/devices",
            {"occupancy": True},
            ["zigbee2mqtt", "bridge", "devices"],
        )
        harness.automation_engine.trigger_event.assert_not_called()
        scheduled_coros.assert_not_called()

    def test_ha_binary_sensor_motion(self, harness, scheduled_coros):
        harness._trigger_motion_event(
            "hems/home/living_room/binary_sensor/living_motion/state",
            {"state": "on", "device_class": "motion"},
            ["hems", "home", "living_room", "binary_sensor", "living_motion", "state"],
        )
        harness.automation_engine.trigger_event.assert_called_once_with("motion:living_motion")
        scheduled_coros.assert_called_once()

    def test_ha_binary_sensor_presence(self, harness, scheduled_coros):
        harness._trigger_motion_event(
            "hems/home/entrance/binary_sensor/entrance_presence/state",
            {"state": "detected", "device_class": "presence"},
            ["hems", "home", "entrance", "binary_sensor", "entrance_presence", "state"],
        )
        harness.automation_engine.trigger_event.assert_called_once_with("motion:entrance_presence")
        scheduled_coros.assert_called_once()

    def test_ha_binary_sensor_off(self, harness, scheduled_coros):
        harness._trigger_motion_event(
            "hems/home/living_room/binary_sensor/living_motion/state",
            {"state": "off", "device_class": "motion"},
            ["hems", "home", "living_room", "binary_sensor", "living_motion", "state"],
        )
        harness.automation_engine.trigger_event.assert_not_called()
        scheduled_coros.assert_not_called()

    def test_non_motion_device_class_ignored(self, harness, scheduled_coros):
        harness._trigger_motion_event(
            "hems/home/living_room/binary_sensor/door/state",
            {"state": "on", "device_class": "door"},
            ["hems", "home", "living_room", "binary_sensor", "door", "state"],
        )
        harness.automation_engine.trigger_event.assert_not_called()
        scheduled_coros.assert_not_called()

    def test_no_automation_engine(self, wm, scheduled_coros):
        harness = _Harness(wm)
        harness.automation_engine = None
        harness._trigger_motion_event(
            "zigbee2mqtt/pir_entrance",
            {"occupancy": True},
            ["zigbee2mqtt", "pir_entrance"],
        )
        scheduled_coros.assert_not_called()

    def test_no_loop(self, harness, scheduled_coros):
        harness._loop = None
        harness._trigger_motion_event(
            "zigbee2mqtt/pir_entrance",
            {"occupancy": True},
            ["zigbee2mqtt", "pir_entrance"],
        )
        harness.automation_engine.trigger_event.assert_not_called()
        scheduled_coros.assert_not_called()
