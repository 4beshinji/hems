"""
Tests for HEMS Lite Sentinel gray zone detector.
Run: python -m pytest tests/lite/test_gray_zone.py -v
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/sentinel/src"))

from state import OccupantState
from gray_zone import GrayZoneDetector


def _make_state_compound() -> OccupantState:
    """Create state with multiple sub-threshold values."""
    s = OccupantState()
    # HR at 70% of threshold (120 * 0.7 = 84, so 100 is above 70%)
    s.update_biometric("heart_rate", 100)
    # Stress at 70% of threshold (80 * 0.7 = 56, so 65 is above 70%)
    s.update_biometric("stress", 65)
    # Fatigue at 70% of threshold (70 * 0.7 = 49, so 55 is above 70%)
    s.update_biometric("fatigue", 55)
    return s


def _make_state_normal() -> OccupantState:
    """Create state with all-normal values."""
    s = OccupantState()
    s.update_biometric("heart_rate", 70)
    s.update_biometric("stress", 30)
    s.update_biometric("fatigue", 20)
    s.update_biometric("spo2", 98)
    return s


class TestCompoundAnomaly:
    def test_detects_compound(self):
        detector = GrayZoneDetector()
        state = _make_state_compound()
        events = detector.evaluate(state)
        compound = [e for e in events if e.pattern == "compound_anomaly"]
        assert len(compound) == 1
        assert len(compound[0].signals) >= 2

    def test_no_compound_when_normal(self):
        detector = GrayZoneDetector()
        state = _make_state_normal()
        events = detector.evaluate(state)
        compound = [e for e in events if e.pattern == "compound_anomaly"]
        assert len(compound) == 0


class TestTrends:
    def test_hr_rising_trend(self):
        detector = GrayZoneDetector()
        state = OccupantState()
        now = time.time()

        # Simulate rising HR over past hours
        for i in range(12):
            ts = now - (12 - i) * 600  # every 10 min
            hr = 70 + i * 3  # 70 → 103
            state._history.setdefault("bio_heart_rate", []).append((ts, hr))

        state.update_biometric("heart_rate", 103)
        events = detector.evaluate(state)
        trend = [e for e in events if e.pattern == "trend"]
        assert len(trend) == 1
        assert "HR" in trend[0].signals[0]

    def test_no_trend_stable(self):
        detector = GrayZoneDetector()
        state = OccupantState()
        now = time.time()

        # Stable HR
        for i in range(12):
            ts = now - (12 - i) * 600
            state._history.setdefault("bio_heart_rate", []).append((ts, 72))

        state.update_biometric("heart_rate", 72)
        events = detector.evaluate(state)
        trend = [e for e in events if e.pattern == "trend"]
        assert len(trend) == 0


class TestContradictions:
    def test_lying_high_hr_daytime(self):
        detector = GrayZoneDetector()
        state = OccupantState()
        state.update_activity("living_room", person_count=1, posture="lying")
        state.update_biometric("heart_rate", 95)

        events = detector.evaluate(state)
        contradictions = [e for e in events if e.pattern == "contradiction"]
        # Depends on time of day — only fires during 6-22h
        hour = time.localtime().tm_hour
        if 6 <= hour <= 22:
            assert len(contradictions) == 1
        else:
            assert len(contradictions) == 0


class TestSensorGap:
    def test_biometric_gap(self):
        detector = GrayZoneDetector()
        state = OccupantState()
        state.biometric_connected = True
        # Set old timestamp (>30 min ago)
        state.heart_rate.timestamp = time.time() - 2400  # 40min ago
        state.heart_rate.value = 72

        events = detector.evaluate(state)
        gaps = [e for e in events if e.pattern == "sensor_gap"]
        assert len(gaps) == 1

    def test_no_gap_when_fresh(self):
        detector = GrayZoneDetector()
        state = OccupantState()
        state.biometric_connected = True
        state.update_biometric("heart_rate", 72)

        events = detector.evaluate(state)
        gaps = [e for e in events if e.pattern == "sensor_gap"]
        assert len(gaps) == 0


class TestCooldowns:
    def test_gray_zone_cooldown(self):
        detector = GrayZoneDetector()
        state = _make_state_compound()

        events1 = detector.evaluate(state)
        events2 = detector.evaluate(state)

        compound1 = [e for e in events1 if e.pattern == "compound_anomaly"]
        compound2 = [e for e in events2 if e.pattern == "compound_anomaly"]

        assert len(compound1) == 1
        assert len(compound2) == 0  # Cooled down
