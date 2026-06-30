"""Tests for TrajectoryRecorder."""

from feedback.trajectory_recorder import TrajectoryRecorder


class FakeEventWriter:
    def __init__(self):
        self.trajectories = []

    def record_trajectory(self, **kwargs):
        self.trajectories.append(kwargs)


def test_finalize_writes_trajectory():
    writer = FakeEventWriter()
    recorder = TrajectoryRecorder(event_writer=writer)
    recorder.record_decision(
        cycle_id="c1",
        decision_id="d1",
        trigger_events=[{"event": "temp_high"}],
        tool_calls=[{"tool": "set_ac"}],
        world_state_snapshot={"zone": "main"},
    )
    trajectory = recorder.finalize("c1", {"feedback_type": "explicit_up"})
    assert trajectory is not None
    assert trajectory["outcome_summary"]["feedback_type"] == "explicit_up"
    assert len(writer.trajectories) == 1
    assert writer.trajectories[0]["cycle_id"] == "c1"


def test_finalize_without_decision_returns_none():
    writer = FakeEventWriter()
    recorder = TrajectoryRecorder(event_writer=writer)
    assert recorder.finalize("missing", {}) is None
    assert len(writer.trajectories) == 0
