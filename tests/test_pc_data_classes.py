"""
Tests for PCState behavior (event ring buffer + mutable-default isolation).

Trivial dataclass field default/assignment tests dropped — Python's @dataclass
already guarantees that, so re-asserting was duplicating language behavior.
"""

from world_model.data_classes import Event, PCState


class TestPCState:
    def test_add_event(self):
        pc = PCState()
        pc.add_event(Event(event_type="test", description="Test event", severity=1))
        assert len(pc.events) == 1
        assert pc.events[0].event_type == "test"

    def test_event_ring_buffer(self):
        pc = PCState(max_events=5)
        for i in range(10):
            pc.add_event(Event(event_type=f"ev_{i}", description=f"Event {i}"))
        assert len(pc.events) == 5
        assert pc.events[0].event_type == "ev_5"
        assert pc.events[-1].event_type == "ev_9"

    def test_independent_instances(self):
        """Default factories must produce independent mutable state per instance."""
        pc1 = PCState()
        pc2 = PCState()
        pc1.add_event(Event(event_type="only_in_pc1"))
        assert len(pc1.events) == 1
        assert len(pc2.events) == 0
