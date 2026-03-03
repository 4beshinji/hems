"""
Tests for Zigbee sensor rules in RuleEngine.
"""
import time
from unittest.mock import patch
from datetime import datetime

import pytest
from rule_engine import RuleEngine
from world_model.data_classes import (
    BinarySensorState, HASensorState, LightState, OccupancyData,
)


@pytest.fixture
def engine():
    e = RuleEngine()
    e._cooldowns = {}
    return e


class TestMoistureRule:
    """Z1: Moisture emergency."""

    def test_moisture_detected_creates_task_and_speaks(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.binary_sensors["binary_sensor.kitchen_leak"] = BinarySensorState(
            entity_id="binary_sensor.kitchen_leak", state=True, device_class="moisture",
        )
        actions = engine.evaluate(world_model)
        task_actions = [a for a in actions if a["tool"] == "create_task" and "水漏れ" in a["args"]["title"]]
        speak_actions = [a for a in actions if a["tool"] == "speak" and "水漏れ" in a["args"]["message"]]
        assert len(task_actions) >= 1
        assert task_actions[0]["args"]["urgency"] == 4
        assert len(speak_actions) >= 1

    def test_moisture_off_no_action(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.binary_sensors["binary_sensor.leak"] = BinarySensorState(
            entity_id="binary_sensor.leak", state=False, device_class="moisture",
        )
        actions = engine.evaluate(world_model)
        moisture_actions = [a for a in actions if "水漏れ" in str(a)]
        assert len(moisture_actions) == 0

    def test_moisture_cooldown(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.binary_sensors["binary_sensor.leak"] = BinarySensorState(
            entity_id="binary_sensor.leak", state=True, device_class="moisture",
        )
        engine.evaluate(world_model)
        actions2 = engine.evaluate(world_model)
        moisture_actions = [a for a in actions2 if "水漏れ" in str(a)]
        assert len(moisture_actions) == 0


class TestDoorArrivalDepartureRule:
    """Z2: Door arrival/departure."""

    def test_door_arrival_lights_on(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        now = time.time()
        world_model.home_devices.binary_sensors["binary_sensor.door"] = BinarySensorState(
            entity_id="binary_sensor.door", state=False, device_class="door",
            previous_state=True, last_changed=now,
        )
        world_model.home_devices.lights["light.living"] = LightState(
            entity_id="light.living", on=False,
        )
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(count=1)

        actions = engine.evaluate(world_model)
        speak_actions = [a for a in actions if a["tool"] == "speak" and "おかえり" in a["args"]["message"]]
        light_actions = [a for a in actions if a["tool"] == "control_light" and a["args"]["on"] is True]
        assert len(speak_actions) >= 1
        assert len(light_actions) >= 1

    def test_door_departure_lights_off(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        now = time.time()
        world_model.home_devices.binary_sensors["binary_sensor.door"] = BinarySensorState(
            entity_id="binary_sensor.door", state=False, device_class="door",
            previous_state=True, last_changed=now,
        )
        world_model.home_devices.lights["light.living"] = LightState(
            entity_id="light.living", on=True,
        )
        # No occupants
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(count=0)

        actions = engine.evaluate(world_model)
        speak_actions = [a for a in actions if a["tool"] == "speak" and "いってらっしゃい" in a["args"]["message"]]
        light_off = [a for a in actions if a["tool"] == "control_light" and a["args"]["on"] is False]
        assert len(speak_actions) >= 1
        assert len(light_off) >= 1

    def test_old_door_event_ignored(self, engine, world_model):
        """Door transition older than 60s is ignored."""
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.binary_sensors["binary_sensor.door"] = BinarySensorState(
            entity_id="binary_sensor.door", state=False, device_class="door",
            previous_state=True, last_changed=time.time() - 120,
        )
        actions = engine.evaluate(world_model)
        door_actions = [a for a in actions if "おかえり" in str(a) or "いってらっしゃい" in str(a)]
        assert len(door_actions) == 0


class TestPowerDropRule:
    """Z3: Appliance finished (power drop to idle)."""

    def test_washer_finished_creates_task(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.sensors["sensor.washer_power"] = HASensorState(
            entity_id="sensor.washer_power", value=2, device_class="power",
            previous_value=200,
        )
        actions = engine.evaluate(world_model)
        task_actions = [a for a in actions if a["tool"] == "create_task" and "洗濯" in a["args"]["title"]]
        speak_actions = [a for a in actions if a["tool"] == "speak" and "洗濯" in a["args"]["message"]]
        assert len(task_actions) >= 1
        assert len(speak_actions) >= 1

    def test_kettle_finished_speak_only(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.sensors["sensor.kettle_power"] = HASensorState(
            entity_id="sensor.kettle_power", value=1, device_class="power",
            previous_value=1500,
        )
        actions = engine.evaluate(world_model)
        speak_actions = [a for a in actions if a["tool"] == "speak" and "お湯" in a["args"]["message"]]
        task_actions = [a for a in actions if a["tool"] == "create_task"]
        assert len(speak_actions) >= 1
        assert len(task_actions) == 0

    def test_generic_appliance_speak(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.sensors["sensor.dryer_power"] = HASensorState(
            entity_id="sensor.dryer_power", value=0, device_class="power",
            previous_value=500,
        )
        actions = engine.evaluate(world_model)
        speak_actions = [a for a in actions if a["tool"] == "speak" and "完了" in a["args"]["message"]]
        assert len(speak_actions) >= 1

    def test_no_action_when_still_running(self, engine, world_model):
        """No action when power is still above idle threshold."""
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.sensors["sensor.washer_power"] = HASensorState(
            entity_id="sensor.washer_power", value=100, device_class="power",
            previous_value=200,
        )
        actions = engine.evaluate(world_model)
        power_actions = [a for a in actions if "完了" in str(a) or "洗濯" in str(a) or "お湯" in str(a)]
        assert len(power_actions) == 0


class TestCO2WindowRule:
    """Z4: CO2 high + all windows closed."""

    def test_co2_high_windows_closed(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.sensors["sensor.co2"] = HASensorState(
            entity_id="sensor.co2", value=1200, device_class="carbon_dioxide",
        )
        world_model.home_devices.binary_sensors["binary_sensor.window"] = BinarySensorState(
            entity_id="binary_sensor.window", state=False, device_class="window",
        )
        actions = engine.evaluate(world_model)
        speak_actions = [a for a in actions if a["tool"] == "speak" and "換気" in a["args"]["message"]]
        assert len(speak_actions) >= 1

    def test_co2_high_window_open_no_action(self, engine, world_model):
        """No suggestion when windows are already open."""
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.sensors["sensor.co2"] = HASensorState(
            entity_id="sensor.co2", value=1200, device_class="carbon_dioxide",
        )
        world_model.home_devices.binary_sensors["binary_sensor.window"] = BinarySensorState(
            entity_id="binary_sensor.window", state=True, device_class="window",
        )
        actions = engine.evaluate(world_model)
        co2_window = [a for a in actions if a["tool"] == "speak" and "窓を開けて換気" in a["args"].get("message", "")]
        assert len(co2_window) == 0

    def test_co2_normal_no_action(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.sensors["sensor.co2"] = HASensorState(
            entity_id="sensor.co2", value=500, device_class="carbon_dioxide",
        )
        world_model.home_devices.binary_sensors["binary_sensor.window"] = BinarySensorState(
            entity_id="binary_sensor.window", state=False, device_class="window",
        )
        actions = engine.evaluate(world_model)
        co2_window = [a for a in actions if a["tool"] == "speak" and "窓を開けて換気" in a["args"].get("message", "")]
        assert len(co2_window) == 0


class TestPM25Rule:
    """Z5: PM2.5 high → purifier on."""

    def test_pm25_high_speaks_and_turns_on_purifier(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.sensors["sensor.pm25"] = HASensorState(
            entity_id="sensor.pm25", value=50, device_class="pm25",
        )
        world_model.home_devices.switches["switch.air_purifier"] = False
        actions = engine.evaluate(world_model)
        speak_actions = [a for a in actions if a["tool"] == "speak" and "PM2.5" in a["args"]["message"]]
        switch_actions = [a for a in actions if a["tool"] == "control_switch"
                          and a["args"]["entity_id"] == "switch.air_purifier"]
        assert len(speak_actions) >= 1
        assert len(switch_actions) >= 1
        assert switch_actions[0]["args"]["on"] is True

    def test_pm25_normal_no_action(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.sensors["sensor.pm25"] = HASensorState(
            entity_id="sensor.pm25", value=20, device_class="pm25",
        )
        actions = engine.evaluate(world_model)
        pm_actions = [a for a in actions if "PM2.5" in str(a)]
        assert len(pm_actions) == 0


class TestVibrationRule:
    """Z6: Vibration stopped (washing machine)."""

    def test_washer_vibration_stopped(self, engine, world_model):
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.binary_sensors["binary_sensor.washing_vibration"] = BinarySensorState(
            entity_id="binary_sensor.washing_vibration", state=False,
            device_class="vibration", previous_state=True,
        )
        actions = engine.evaluate(world_model)
        task_actions = [a for a in actions if a["tool"] == "create_task" and "洗濯" in a["args"]["title"]]
        speak_actions = [a for a in actions if a["tool"] == "speak" and "洗濯" in a["args"]["message"]]
        assert len(task_actions) >= 1
        assert len(speak_actions) >= 1

    def test_non_washing_vibration_no_action(self, engine, world_model):
        """Vibration sensor not matching washing keywords is ignored."""
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.binary_sensors["binary_sensor.desk_vibration"] = BinarySensorState(
            entity_id="binary_sensor.desk_vibration", state=False,
            device_class="vibration", previous_state=True,
        )
        actions = engine.evaluate(world_model)
        vib_actions = [a for a in actions if "洗濯" in str(a)]
        assert len(vib_actions) == 0


class TestCriticalMoisture:
    """Moisture should fire in evaluate_critical (low-power mode)."""

    def test_critical_moisture_fires(self, engine, world_model):
        world_model.home_devices.binary_sensors["binary_sensor.leak"] = BinarySensorState(
            entity_id="binary_sensor.leak", state=True, device_class="moisture",
        )
        actions = engine.evaluate_critical(world_model)
        task_actions = [a for a in actions if a["tool"] == "create_task" and "水漏れ" in a["args"]["title"]]
        speak_actions = [a for a in actions if a["tool"] == "speak" and "水漏れ" in a["args"]["message"]]
        assert len(task_actions) >= 1
        assert len(speak_actions) >= 1

    def test_critical_no_moisture_when_dry(self, engine, world_model):
        world_model.home_devices.binary_sensors["binary_sensor.leak"] = BinarySensorState(
            entity_id="binary_sensor.leak", state=False, device_class="moisture",
        )
        actions = engine.evaluate_critical(world_model)
        moisture_actions = [a for a in actions if "水漏れ" in str(a)]
        assert len(moisture_actions) == 0
