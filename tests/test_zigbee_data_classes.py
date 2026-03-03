"""
Tests for Zigbee binary sensor / HA sensor data classes.
"""
from world_model.data_classes import (
    BinarySensorState, HASensorState, HomeDevicesState, Event,
)


class TestBinarySensorState:
    def test_default_values(self):
        bs = BinarySensorState()
        assert bs.entity_id == ""
        assert bs.state is False
        assert bs.device_class == ""
        assert bs.last_update == 0
        assert bs.last_changed == 0
        assert bs.previous_state is False

    def test_door_open(self):
        bs = BinarySensorState(
            entity_id="binary_sensor.front_door",
            state=True,
            device_class="door",
            last_update=100.0,
            last_changed=100.0,
        )
        assert bs.entity_id == "binary_sensor.front_door"
        assert bs.state is True
        assert bs.device_class == "door"

    def test_moisture_detected(self):
        bs = BinarySensorState(
            entity_id="binary_sensor.kitchen_leak",
            state=True,
            device_class="moisture",
            previous_state=False,
        )
        assert bs.state is True
        assert bs.previous_state is False

    def test_state_transition_tracking(self):
        bs = BinarySensorState(
            entity_id="binary_sensor.window",
            state=False,
            device_class="window",
            previous_state=True,
            last_changed=200.0,
        )
        assert bs.state is False
        assert bs.previous_state is True
        assert bs.last_changed == 200.0


class TestHASensorState:
    def test_default_values(self):
        s = HASensorState()
        assert s.entity_id == ""
        assert s.value == 0
        assert s.unit == ""
        assert s.device_class == ""
        assert s.last_update == 0
        assert s.previous_value == 0

    def test_power_sensor(self):
        s = HASensorState(
            entity_id="sensor.washer_power",
            value=120.5,
            unit="W",
            device_class="power",
            previous_value=200.0,
        )
        assert s.value == 120.5
        assert s.unit == "W"
        assert s.device_class == "power"
        assert s.previous_value == 200.0

    def test_co2_sensor(self):
        s = HASensorState(
            entity_id="sensor.living_co2",
            value=850,
            unit="ppm",
            device_class="carbon_dioxide",
        )
        assert s.value == 850
        assert s.device_class == "carbon_dioxide"


class TestHomeDevicesStateBinarySensors:
    def test_binary_sensors_field_exists(self):
        hd = HomeDevicesState()
        assert hd.binary_sensors == {}
        assert hd.sensors == {}

    def test_add_binary_sensors(self):
        hd = HomeDevicesState()
        hd.binary_sensors["binary_sensor.door"] = BinarySensorState(
            entity_id="binary_sensor.door", state=True, device_class="door",
        )
        hd.sensors["sensor.power"] = HASensorState(
            entity_id="sensor.power", value=100, device_class="power",
        )
        assert len(hd.binary_sensors) == 1
        assert len(hd.sensors) == 1
        assert hd.binary_sensors["binary_sensor.door"].state is True
        assert hd.sensors["sensor.power"].value == 100

    def test_coexistence_with_existing_fields(self):
        """binary_sensors and sensors coexist with lights/climates/covers/switches."""
        from world_model.data_classes import LightState
        hd = HomeDevicesState()
        hd.lights["light.a"] = LightState(entity_id="light.a", on=True)
        hd.binary_sensors["bs.a"] = BinarySensorState(entity_id="bs.a", state=True)
        hd.sensors["s.a"] = HASensorState(entity_id="s.a", value=42)
        assert len(hd.lights) == 1
        assert len(hd.binary_sensors) == 1
        assert len(hd.sensors) == 1
