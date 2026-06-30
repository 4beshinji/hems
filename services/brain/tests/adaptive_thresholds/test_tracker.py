"""Tests for MetricDriftTracker."""

import pytest

from adaptive_thresholds.tracker import MetricDriftTracker

pytestmark = pytest.mark.skipif(
    pytest.importorskip("river", reason="river not installed") is None,
    reason="river not installed",
)


def test_tracker_requires_min_samples_before_drift():
    tracker = MetricDriftTracker("co2_high", min_samples=10)
    for _ in range(5):
        result = tracker.update(400.0, current_threshold=1000.0)
    assert not result.drift_detected


def test_tracker_detects_distribution_shift():
    tracker = MetricDriftTracker("co2_high", detector="adwin", delta=0.01, min_samples=10)
    # Stable baseline
    for _ in range(40):
        tracker.update(400.0, current_threshold=1000.0)
    # Sudden shift
    detected = False
    for _ in range(50):
        result = tracker.update(1200.0, current_threshold=1000.0)
        if result.drift_detected:
            detected = True
            break
    assert detected
    assert result.proposed_threshold is not None


def test_tracker_proposal_respects_clamp():
    tracker = MetricDriftTracker("co2_high", detector="adwin", delta=0.01, min_samples=10, clamp=(-50.0, 50.0))
    for _ in range(40):
        tracker.update(400.0, current_threshold=1000.0)
    for _ in range(50):
        result = tracker.update(2000.0, current_threshold=1000.0)
        if result.drift_detected:
            break
    assert result.proposed_threshold is not None
    # offset should be clamped to 50
    assert result.proposed_threshold == 1050.0


def test_tracker_state_serializable():
    tracker = MetricDriftTracker("temp_high")
    state = tracker.get_state()
    assert state["metric_key"] == "temp_high"
    assert "samples" in state
