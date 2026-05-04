"""
Tests for GASState behavior (event ring buffer + default-factory isolation).

Trivial dataclass field default/assignment tests dropped — covered by Python.
"""

from world_model.data_classes import Event, GASState


class TestGASState:
    def test_event_ring_buffer(self):
        gs = GASState(max_events=5)
        for i in range(10):
            gs.add_event(Event(event_type=f"ev_{i}", description=f"Event {i}"))
        assert len(gs.events) == 5
        assert gs.events[0].event_type == "ev_5"
        assert gs.events[-1].event_type == "ev_9"

    def test_independent_instances(self):
        """Default factories must produce independent lists per instance."""
        gs1 = GASState()
        gs2 = GASState()
        gs1.add_event(Event(event_type="only_in_gs1"))
        assert len(gs2.events) == 0
        assert len(gs1.calendar_events) == 0  # also independent
