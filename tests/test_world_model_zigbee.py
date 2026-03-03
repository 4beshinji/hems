"""
Tests for WorldModel Zigbee binary_sensor/sensor MQTT processing,
event generation, and LLM context display.
"""
import pytest
from world_model.data_classes import BinarySensorState, HASensorState, LightState


class TestBinarySensorMQTT:
    def test_door_open_from_mqtt(self, world_model):
        """binary_sensor with state=open creates BinarySensorState."""
        world_model.update_from_mqtt(
            "hems/home/living_room/binary_sensor/binary_sensor.front_door/state",
            {"state": "open", "device_class": "door"},
        )
        hd = world_model.home_devices
        assert "binary_sensor.front_door" in hd.binary_sensors
        bs = hd.binary_sensors["binary_sensor.front_door"]
        assert bs.state is True
        assert bs.device_class == "door"

    def test_door_closed_from_mqtt(self, world_model):
        """binary_sensor with state=off is False."""
        world_model.update_from_mqtt(
            "hems/home/living_room/binary_sensor/binary_sensor.front_door/state",
            {"state": "off", "device_class": "door"},
        )
        bs = world_model.home_devices.binary_sensors["binary_sensor.front_door"]
        assert bs.state is False

    def test_moisture_detected(self, world_model):
        """binary_sensor with state=wet is True."""
        world_model.update_from_mqtt(
            "hems/home/kitchen/binary_sensor/binary_sensor.leak/state",
            {"state": "wet", "device_class": "moisture"},
        )
        bs = world_model.home_devices.binary_sensors["binary_sensor.leak"]
        assert bs.state is True
        assert bs.device_class == "moisture"

    def test_previous_state_tracking(self, world_model):
        """previous_state is set on state transition."""
        topic = "hems/home/living_room/binary_sensor/binary_sensor.door/state"
        world_model.update_from_mqtt(topic, {"state": "open", "device_class": "door"})
        bs = world_model.home_devices.binary_sensors["binary_sensor.door"]
        assert bs.state is True

        world_model.update_from_mqtt(topic, {"state": "off", "device_class": "door"})
        bs = world_model.home_devices.binary_sensors["binary_sensor.door"]
        assert bs.state is False
        assert bs.previous_state is True

    def test_last_changed_on_transition(self, world_model):
        """last_changed updates only on actual state change."""
        topic = "hems/home/living_room/binary_sensor/binary_sensor.door/state"
        world_model.update_from_mqtt(topic, {"state": "open", "device_class": "door"})
        first_changed = world_model.home_devices.binary_sensors["binary_sensor.door"].last_changed

        # Same state again - last_changed should NOT change
        world_model.update_from_mqtt(topic, {"state": "on", "device_class": "door"})
        bs = world_model.home_devices.binary_sensors["binary_sensor.door"]
        assert bs.last_changed == first_changed

    def test_device_class_preserved(self, world_model):
        """device_class from first message persists even if omitted later."""
        topic = "hems/home/living_room/binary_sensor/binary_sensor.motion/state"
        world_model.update_from_mqtt(topic, {"state": "on", "device_class": "motion"})
        world_model.update_from_mqtt(topic, {"state": "off"})
        bs = world_model.home_devices.binary_sensors["binary_sensor.motion"]
        assert bs.device_class == "motion"


class TestBinarySensorEvents:
    def test_door_open_event(self, world_model):
        """Opening a door generates door_opened event."""
        world_model.update_from_mqtt(
            "hems/home/living_room/binary_sensor/binary_sensor.door/state",
            {"state": "off", "device_class": "door"},
        )
        world_model.update_from_mqtt(
            "hems/home/living_room/binary_sensor/binary_sensor.door/state",
            {"state": "open", "device_class": "door"},
        )
        events = [e for e in world_model.home_devices.events if e.event_type == "door_opened"]
        assert len(events) == 1

    def test_door_closed_event(self, world_model):
        """Closing a door generates door_closed event."""
        world_model.update_from_mqtt(
            "hems/home/living_room/binary_sensor/binary_sensor.door/state",
            {"state": "open", "device_class": "door"},
        )
        world_model.update_from_mqtt(
            "hems/home/living_room/binary_sensor/binary_sensor.door/state",
            {"state": "off", "device_class": "door"},
        )
        events = [e for e in world_model.home_devices.events if e.event_type == "door_closed"]
        assert len(events) == 1

    def test_moisture_event(self, world_model):
        """Moisture detection generates moisture_detected event."""
        world_model.update_from_mqtt(
            "hems/home/kitchen/binary_sensor/binary_sensor.leak/state",
            {"state": "off", "device_class": "moisture"},
        )
        world_model.update_from_mqtt(
            "hems/home/kitchen/binary_sensor/binary_sensor.leak/state",
            {"state": "wet", "device_class": "moisture"},
        )
        events = [e for e in world_model.home_devices.events if e.event_type == "moisture_detected"]
        assert len(events) == 1
        assert events[0].severity == 2

    def test_vibration_stopped_event(self, world_model):
        """Vibration stopping generates vibration_stopped event."""
        world_model.update_from_mqtt(
            "hems/home/laundry/binary_sensor/binary_sensor.washer_vib/state",
            {"state": "on", "device_class": "vibration"},
        )
        world_model.update_from_mqtt(
            "hems/home/laundry/binary_sensor/binary_sensor.washer_vib/state",
            {"state": "off", "device_class": "vibration"},
        )
        events = [e for e in world_model.home_devices.events if e.event_type == "vibration_stopped"]
        assert len(events) == 1


class TestHASensorMQTT:
    def test_power_sensor_from_mqtt(self, world_model):
        """sensor domain creates HASensorState."""
        world_model.update_from_mqtt(
            "hems/home/kitchen/sensor/sensor.washer_power/state",
            {"state": "150.5", "device_class": "power", "unit_of_measurement": "W"},
        )
        hd = world_model.home_devices
        assert "sensor.washer_power" in hd.sensors
        s = hd.sensors["sensor.washer_power"]
        assert s.value == 150.5
        assert s.unit == "W"
        assert s.device_class == "power"

    def test_unknown_state_becomes_zero(self, world_model):
        """sensor with state=unknown resolves to 0."""
        world_model.update_from_mqtt(
            "hems/home/kitchen/sensor/sensor.test/state",
            {"state": "unknown", "device_class": "power"},
        )
        assert world_model.home_devices.sensors["sensor.test"].value == 0

    def test_unavailable_state_becomes_zero(self, world_model):
        """sensor with state=unavailable resolves to 0."""
        world_model.update_from_mqtt(
            "hems/home/kitchen/sensor/sensor.test/state",
            {"state": "unavailable", "device_class": "temperature"},
        )
        assert world_model.home_devices.sensors["sensor.test"].value == 0

    def test_previous_value_tracking(self, world_model):
        """previous_value tracks the last known value."""
        topic = "hems/home/kitchen/sensor/sensor.washer_power/state"
        world_model.update_from_mqtt(topic, {"state": "200", "device_class": "power"})
        world_model.update_from_mqtt(topic, {"state": "3", "device_class": "power"})
        s = world_model.home_devices.sensors["sensor.washer_power"]
        assert s.value == 3
        assert s.previous_value == 200

    def test_power_drop_idle_event(self, world_model):
        """Power drop below POWER_IDLE_WATTS generates power_drop_idle event."""
        topic = "hems/home/kitchen/sensor/sensor.washer_power/state"
        world_model.update_from_mqtt(topic, {"state": "200", "device_class": "power"})
        world_model.update_from_mqtt(topic, {"state": "2", "device_class": "power"})
        events = [e for e in world_model.home_devices.events if e.event_type == "power_drop_idle"]
        assert len(events) == 1

    def test_no_event_when_already_idle(self, world_model):
        """No event when power was already below threshold."""
        topic = "hems/home/kitchen/sensor/sensor.test/state"
        world_model.update_from_mqtt(topic, {"state": "3", "device_class": "power"})
        world_model.update_from_mqtt(topic, {"state": "1", "device_class": "power"})
        events = [e for e in world_model.home_devices.events if e.event_type == "power_drop_idle"]
        assert len(events) == 0

    def test_device_class_preserved(self, world_model):
        """device_class from first message persists."""
        topic = "hems/home/room/sensor/sensor.co2/state"
        world_model.update_from_mqtt(topic, {"state": "800", "device_class": "carbon_dioxide", "unit_of_measurement": "ppm"})
        world_model.update_from_mqtt(topic, {"state": "900"})
        s = world_model.home_devices.sensors["sensor.co2"]
        assert s.device_class == "carbon_dioxide"
        assert s.unit == "ppm"


class TestLLMContextZigbee:
    def test_moisture_sensor_always_shown(self, world_model):
        """Moisture binary_sensor always appears in context."""
        hd = world_model.home_devices
        hd.bridge_connected = True
        hd.binary_sensors["binary_sensor.leak"] = BinarySensorState(
            entity_id="binary_sensor.leak", state=False, device_class="moisture",
        )
        context = world_model.get_llm_context()
        assert "水漏れ" in context

    def test_moisture_detected_has_warning(self, world_model):
        """Active moisture sensor shows warning marker."""
        hd = world_model.home_devices
        hd.bridge_connected = True
        hd.binary_sensors["binary_sensor.leak"] = BinarySensorState(
            entity_id="binary_sensor.leak", state=True, device_class="moisture",
        )
        context = world_model.get_llm_context()
        assert "⚠" in context
        assert "検知" in context

    def test_active_door_shown(self, world_model):
        """Open door shown in context."""
        hd = world_model.home_devices
        hd.bridge_connected = True
        hd.binary_sensors["binary_sensor.door"] = BinarySensorState(
            entity_id="binary_sensor.door", state=True, device_class="door",
        )
        context = world_model.get_llm_context()
        assert "ドア" in context
        assert "検知中" in context

    def test_closed_door_not_shown(self, world_model):
        """Closed door (state=False, not moisture) not shown."""
        hd = world_model.home_devices
        hd.bridge_connected = True
        hd.binary_sensors["binary_sensor.door"] = BinarySensorState(
            entity_id="binary_sensor.door", state=False, device_class="door",
        )
        context = world_model.get_llm_context()
        assert "ドア" not in context

    def test_power_sensor_shown(self, world_model):
        """Power sensor with value > 0 shown."""
        hd = world_model.home_devices
        hd.bridge_connected = True
        hd.sensors["sensor.washer_power"] = HASensorState(
            entity_id="sensor.washer_power", value=120, unit="W", device_class="power",
        )
        context = world_model.get_llm_context()
        assert "電力" in context
        assert "120" in context

    def test_zero_power_not_shown(self, world_model):
        """Power sensor with value=0 not shown."""
        hd = world_model.home_devices
        hd.bridge_connected = True
        hd.sensors["sensor.washer_power"] = HASensorState(
            entity_id="sensor.washer_power", value=0, unit="W", device_class="power",
        )
        context = world_model.get_llm_context()
        assert "電力" not in context

    def test_co2_sensor_shown(self, world_model):
        """CO2 sensor always shown."""
        hd = world_model.home_devices
        hd.bridge_connected = True
        hd.sensors["sensor.co2"] = HASensorState(
            entity_id="sensor.co2", value=800, unit="ppm", device_class="carbon_dioxide",
        )
        context = world_model.get_llm_context()
        assert "CO2" in context
        assert "800" in context

    def test_pm25_sensor_shown(self, world_model):
        """PM2.5 sensor shown."""
        hd = world_model.home_devices
        hd.bridge_connected = True
        hd.sensors["sensor.pm25"] = HASensorState(
            entity_id="sensor.pm25", value=25, unit="µg/m³", device_class="pm25",
        )
        context = world_model.get_llm_context()
        assert "PM2.5" in context
