"""
Tests for Home Assistant device data classes.
"""

from world_model.data_classes import (
    ClimateState,
    CoverState,
    Event,
    HomeDevicesState,
    LightState,
)


class TestLightState:
    def test_default_values(self):
        lt = LightState()
        assert lt.entity_id == ""
        assert lt.on is False
        assert lt.brightness == 0
        assert lt.color_temp == 0
        assert lt.last_update == 0

    def test_custom_values(self):
        lt = LightState(entity_id="light.living_room", on=True, brightness=200, color_temp=300)
        assert lt.entity_id == "light.living_room"
        assert lt.on is True
        assert lt.brightness == 200
        assert lt.color_temp == 300


class TestClimateState:
    def test_default_values(self):
        c = ClimateState()
        assert c.entity_id == ""
        assert c.mode == "off"
        assert c.target_temp == 0
        assert c.current_temp == 0
        assert c.fan_mode == "auto"

    def test_custom_values(self):
        c = ClimateState(entity_id="climate.living_room", mode="cool", target_temp=26, current_temp=28.5)
        assert c.mode == "cool"
        assert c.target_temp == 26
        assert c.current_temp == 28.5


class TestCoverState:
    def test_default_values(self):
        c = CoverState()
        assert c.entity_id == ""
        assert c.position == 0
        assert c.is_open is False

    def test_open_cover(self):
        c = CoverState(entity_id="cover.bedroom", position=100, is_open=True)
        assert c.is_open is True
        assert c.position == 100


class TestHomeDevicesState:
    def test_default_empty(self):
        hd = HomeDevicesState()
        assert hd.lights == {}
        assert hd.climates == {}
        assert hd.covers == {}
        assert hd.switches == {}
        assert hd.bridge_connected is False
        assert hd.events == []

    def test_add_devices(self):
        hd = HomeDevicesState()
        hd.lights["light.living"] = LightState(entity_id="light.living", on=True)
        hd.climates["climate.living"] = ClimateState(entity_id="climate.living", mode="cool")
        hd.covers["cover.bedroom"] = CoverState(entity_id="cover.bedroom", position=50)
        hd.switches["switch.plug"] = True

        assert len(hd.lights) == 1
        assert len(hd.climates) == 1
        assert len(hd.covers) == 1
        assert hd.switches["switch.plug"] is True

    def test_event_ring_buffer(self):
        hd = HomeDevicesState(max_events=3)
        for i in range(5):
            hd.add_event(Event(event_type=f"test_{i}"))
        assert len(hd.events) == 3
        assert hd.events[0].event_type == "test_2"

    def test_lights_on_off(self):
        hd = HomeDevicesState()
        hd.lights["light.a"] = LightState(entity_id="light.a", on=True, brightness=200)
        hd.lights["light.b"] = LightState(entity_id="light.b", on=False)

        on_lights = [lt for lt in hd.lights.values() if lt.on]
        off_lights = [lt for lt in hd.lights.values() if not lt.on]
        assert len(on_lights) == 1
        assert len(off_lights) == 1
