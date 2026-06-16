"""Tests for inbound MQTT sensor payload validation (Group B, ported from SOMS).

Covers the validation primitive plus the two world-model ingestion paths that
feed sensor fusion (hems/sensors/* topics and zigbee2mqtt direct). The
event-store persistence path lives in main.py::_process_mqtt and gets its
integration test once the brain mixin split (Wave 5) makes it isolable.
"""

import pytest

from world_model.sensor_validation import NUMERIC_RANGES, validate_sensor_value
from world_model.world_model import WorldModel


class TestValidateSensorValue:
    @pytest.mark.parametrize(
        "channel,value,expected",
        [
            ("temperature", 22.5, 22.5),
            ("temperature", -40.0, -40.0),  # boundary low
            ("temperature", 60.0, 60.0),  # boundary high
            ("humidity", 0, 0.0),
            ("humidity", 100, 100.0),
            ("co2", 800, 800.0),
            ("pressure", 1013.25, 1013.25),
            ("light", 100000, 100000.0),
            ("illuminance", 100000, 100000.0),
        ],
    )
    def test_in_range_accepted(self, channel, value, expected):
        ok, coerced = validate_sensor_value(channel, value)
        assert ok is True
        assert coerced == expected

    @pytest.mark.parametrize(
        "channel,value",
        [
            ("temperature", 999.0),  # injected absurd heat
            ("temperature", -100.0),
            ("humidity", 150),  # >100%
            ("humidity", -5),
            ("co2", 999999),  # absurd ppm
            ("pressure", 50.0),  # implausible
            ("light", -1),
        ],
    )
    def test_out_of_range_rejected(self, channel, value):
        ok, coerced = validate_sensor_value(channel, value)
        assert ok is False
        assert coerced is None

    @pytest.mark.parametrize("value", ["hot", "DROP TABLE", None, [1, 2], {"a": 1}, "NaN"])
    def test_non_numeric_rejected(self, value):
        ok, coerced = validate_sensor_value("temperature", value)
        assert ok is False
        assert coerced is None

    def test_nan_and_inf_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            ok, coerced = validate_sensor_value("temperature", bad)
            assert ok is False
            assert coerced is None

    def test_numeric_string_coerced(self):
        ok, coerced = validate_sensor_value("temperature", "22.5")
        assert ok is True
        assert coerced == 22.5

    def test_bool_coerced(self):
        # Edge devices publish JSON booleans; bool must coerce, not reject.
        ok, coerced = validate_sensor_value("door", True)
        assert ok is True
        assert coerced == 1.0

    def test_unknown_channel_numeric_accepted_no_range(self):
        ok, coerced = validate_sensor_value("noise_db", 9999)
        assert ok is True
        assert coerced == 9999.0

    def test_unknown_channel_non_numeric_rejected(self):
        ok, coerced = validate_sensor_value("noise_db", "loud")
        assert ok is False
        assert coerced is None


class TestUpdateFromMqttValidation:
    """hems/sensors/{zone}/sensor/{device}/{channel} → world model (LLM context)."""

    def test_valid_temperature_applied(self):
        wm = WorldModel()
        wm.update_from_mqtt("hems/sensors/kitchen/sensor/env_01/temperature", {"value": 22.5})
        assert wm.zones["kitchen"].environment.temperature == pytest.approx(22.5)

    def test_out_of_range_temperature_dropped(self):
        wm = WorldModel()
        wm.update_from_mqtt("hems/sensors/kitchen/sensor/env_01/temperature", {"value": 999.0})
        # Routing may create the zone, but the injected value never lands.
        assert "kitchen" not in wm.zones or wm.zones["kitchen"].environment.temperature is None

    def test_non_numeric_dropped(self):
        wm = WorldModel()
        wm.update_from_mqtt("hems/sensors/kitchen/sensor/env_01/co2", {"value": "DROP TABLE"})
        assert "kitchen" not in wm.zones or wm.zones["kitchen"].environment.co2 is None

    def test_numeric_string_coerced_and_applied(self):
        wm = WorldModel()
        wm.update_from_mqtt("hems/sensors/kitchen/sensor/env_01/co2", {"value": "600"})
        assert wm.zones["kitchen"].environment.co2 == pytest.approx(600.0)


class TestZigbeeDirectValidation:
    """zigbee2mqtt/{device} analog channels go through the same guard."""

    def test_valid_zigbee_temperature_applied(self):
        wm = WorldModel()
        wm.update_from_mqtt("zigbee2mqtt/temp_01", {"zone": "office", "temperature": 21.0})
        assert wm.zones["office"].environment.temperature == pytest.approx(21.0)

    def test_out_of_range_zigbee_dropped(self):
        wm = WorldModel()
        wm.update_from_mqtt("zigbee2mqtt/temp_01", {"zone": "office", "temperature": 999.0})
        # Dropped before _update_sensor, so the zone is never even created.
        assert "office" not in wm.zones or wm.zones["office"].environment.temperature is None

    def test_illuminance_mapped_to_light(self):
        wm = WorldModel()
        wm.update_from_mqtt("zigbee2mqtt/lux_01", {"zone": "office", "illuminance": 500})
        assert wm.zones["office"].environment.light == pytest.approx(500.0)


def test_all_registry_analog_channels_have_ranges():
    """Every analog channel the world model maps should have a range entry, so
    injections on those high-visibility channels can't bypass validation."""
    from world_model.sensor_fusion import CHANNEL_REGISTRY, ChannelType

    analog = {c for c, t in CHANNEL_REGISTRY.items() if t == ChannelType.ANALOG}
    missing = analog - set(NUMERIC_RANGES)
    assert not missing, f"analog channels without a range: {missing}"
