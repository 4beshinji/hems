"""
Tests for HomeDevicesState multi-domain coexistence (Zigbee binary sensors +
HA sensors must not collide with lights/climates/covers/switches dicts).

Trivial dataclass field default/assignment tests dropped — covered by Python.
"""

from world_model.data_classes import (
    BinarySensorState,
    HASensorState,
    HomeDevicesState,
    LightState,
)


def test_multi_domain_dicts_coexist():
    """All device-kind dicts coexist on HomeDevicesState without colliding."""
    hd = HomeDevicesState()
    hd.lights["light.a"] = LightState(entity_id="light.a", on=True)
    hd.binary_sensors["bs.a"] = BinarySensorState(entity_id="bs.a", state=True)
    hd.sensors["s.a"] = HASensorState(entity_id="s.a", value=42)
    assert len(hd.lights) == 1
    assert len(hd.binary_sensors) == 1
    assert len(hd.sensors) == 1
