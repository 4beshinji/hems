"""
Tests for HomeDevicesState behavior (event ring buffer + dict isolation).

Trivial dataclass field default/assignment tests dropped — covered by Python.
"""

from world_model.data_classes import (
    Event,
    HomeDevicesState,
    LightState,
)


class TestHomeDevicesState:
    def test_event_ring_buffer(self):
        hd = HomeDevicesState(max_events=3)
        for i in range(5):
            hd.add_event(Event(event_type=f"test_{i}"))
        assert len(hd.events) == 3
        assert hd.events[0].event_type == "test_2"

    def test_lights_filter_by_state(self):
        """Iterating hd.lights values to filter on/off should work as a dict."""
        hd = HomeDevicesState()
        hd.lights["light.a"] = LightState(entity_id="light.a", on=True, brightness=200)
        hd.lights["light.b"] = LightState(entity_id="light.b", on=False)
        on_lights = [lt for lt in hd.lights.values() if lt.on]
        assert len(on_lights) == 1
        assert on_lights[0].entity_id == "light.a"
