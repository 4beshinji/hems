"""Tests for AdaptiveThresholdManager."""

import pytest

from adaptive_thresholds.manager import AdaptiveThresholdManager
from rules.config import load_rule_thresholds

pytestmark = pytest.mark.skipif(
    pytest.importorskip("river", reason="river not installed") is None,
    reason="river not installed",
)


@pytest.fixture
def thresholds():
    return load_rule_thresholds()


def test_feed_tracks_adaptable_channel(thresholds):
    manager = AdaptiveThresholdManager(thresholds)
    for _ in range(50):
        results = manager.feed("co2", 400.0)
    assert len(results) == 1
    assert results[0].drift_detected is False


def test_feed_ignores_non_adaptable_channel(thresholds):
    manager = AdaptiveThresholdManager(thresholds)
    results = manager.feed("pressure", 1000.0)
    assert results == []


def test_drift_creates_pending_proposal(thresholds):
    manager = AdaptiveThresholdManager(thresholds)
    # Stable baseline
    for _ in range(40):
        manager.feed("temperature", 20.0)
    # Sudden shift
    detected = False
    for _ in range(30):
        results = manager.feed("temperature", 35.0)
        if any(r.drift_detected for r in results):
            detected = True
            break
    assert detected
    proposals = manager.flush_proposals()
    assert len(proposals) >= 1
    assert proposals[0]["metric_key"] in ("temp_high", "temp_low")


def test_load_adjustments_applies_offsets(thresholds):
    manager = AdaptiveThresholdManager(thresholds)
    manager.load_adjustments(
        [
            {"metric_key": "co2_high", "offset": 50.0},
            {"metric_key": "temp_high", "offset": -1.5},
        ]
    )
    assert manager.get_effective("co2_high") == 1050.0
    assert manager.get_effective("temp_high") == 26.5


def test_set_offset_clamps(thresholds):
    manager = AdaptiveThresholdManager(thresholds)
    manager.set_offset("co2_high", 500.0)
    assert manager.get_offset("co2_high") == 200.0
