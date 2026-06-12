"""
Characterization tests for WorldModel._update_biometric_state (W2.7b).

Purpose: Golden-file baseline for the ~165-line method before the C2 table-driven
refactor.  Every metric branch, threshold-crossing path (including falsy-zero /
prev_is_None edge cases), missing-key guard, and side-effect is pinned here so
any behaviour change during the refactor turns red immediately.

Thresholds (DI via RuleThresholds):
    hr_high=120, hr_low=45, spo2_low=92, stress_high=80
    hrv_low=20, body_temp_high=37.5, respiratory_rate_high=25
"""

import sys
from pathlib import Path

# Ensure brain src is on the path (conftest.py already handles this, but
# duplicate insert is idempotent).
_root = Path(__file__).resolve().parent.parent
_brain_src = str(_root / "services" / "brain" / "src")
if _brain_src not in sys.path:
    sys.path.insert(0, _brain_src)

from rules.config import RuleThresholds
from world_model import WorldModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _thresholds(**overrides) -> RuleThresholds:
    """Build a RuleThresholds with test-friendly defaults, allowing per-test overrides."""
    base = dict(
        temp_critical_high=40.0,
        temp_critical_low=5.0,
        spo2_critical_low=88,
        hr_critical_sleep=150,
        biometric_stale_minutes=30,
        pc_proc_cpu_high=90.0,
        pc_proc_cpu_sustain_s=300,
        pc_proc_mem_high_gb=4.0,
        pc_proc_cooldown_s=1800,
        hr_high=120,
        hr_low=45,
        spo2_low=92,
        stress_high=80,
        hrv_low=20,
        body_temp_high=37.5,
        respiratory_rate_high=25,
    )
    base.update(overrides)
    return RuleThresholds(**base)


def _wm(**threshold_overrides) -> WorldModel:
    """Fresh WorldModel with injected thresholds."""
    return WorldModel(thresholds=_thresholds(**threshold_overrides))


def _call(wm: WorldModel, provider: str, metric: str, payload: dict):
    """Invoke _update_biometric_state via the public path_parts / payload API."""
    wm._update_biometric_state([provider, metric], payload)


def _events(wm: WorldModel) -> list:
    return wm.biometric_state.events


def _event_types(wm: WorldModel) -> list[str]:
    return [e.event_type for e in _events(wm)]


# ---------------------------------------------------------------------------
# Bridge status routing
# ---------------------------------------------------------------------------


class TestBridgeStatus:
    """hems/personal/biometrics/bridge/status is handled before metric dispatch."""

    def test_bridge_connect_sets_flag_and_provider(self):
        wm = _wm()
        wm._update_biometric_state(["bridge", "status"], {"connected": True, "provider": "garmin"})
        bio = wm.biometric_state
        assert bio.bridge_connected is True
        assert bio.provider == "garmin"

    def test_bridge_disconnect_clears_flag(self):
        wm = _wm()
        wm._update_biometric_state(["bridge", "status"], {"connected": True, "provider": "garmin"})
        wm._update_biometric_state(["bridge", "status"], {"connected": False})
        assert wm.biometric_state.bridge_connected is False

    def test_bridge_status_returns_early_no_metric_side_effects(self):
        """bridge/status path must not touch metric sub-objects."""
        wm = _wm()
        wm._update_biometric_state(["bridge", "status"], {"connected": True})
        bio = wm.biometric_state
        assert bio.heart_rate.bpm is None
        assert bio.heart_rate.last_update == 0
        assert _events(wm) == []

    def test_empty_path_parts_is_noop(self):
        wm = _wm()
        wm._update_biometric_state([], {})
        bio = wm.biometric_state
        assert bio.bridge_connected is False
        assert _events(wm) == []

    def test_single_path_part_no_crash(self):
        """Single part (no metric) must return early without error."""
        wm = _wm()
        wm._update_biometric_state(["garmin"], {"bpm": 70})
        assert wm.biometric_state.heart_rate.bpm is None


# ---------------------------------------------------------------------------
# heart_rate metric
# ---------------------------------------------------------------------------


class TestHeartRateUpdate:
    """Normal updates, zone classification, resting_bpm, bridge_connected, history."""

    def test_normal_bpm_updates_fields(self):
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 72, "resting_bpm": 60})
        hr = wm.biometric_state.heart_rate
        assert hr.bpm == 72
        assert hr.resting_bpm == 60
        assert hr.zone == "fat_burn"
        assert hr.last_update > 0

    def test_bridge_connected_set_on_heart_rate(self):
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 72})
        assert wm.biometric_state.bridge_connected is True

    def test_heart_rate_history_recorded(self):
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 72})
        history = wm.biometric_state.history.get("heart_rate")
        assert history is not None
        assert len(history) == 1
        assert history[0][1] == 72.0

    def test_missing_bpm_key_is_noop(self):
        """Payload without 'bpm' key must not update anything."""
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"resting_bpm": 55})
        assert wm.biometric_state.heart_rate.bpm is None
        assert wm.biometric_state.heart_rate.last_update == 0
        assert _events(wm) == []

    def test_zero_bpm_is_falsy_but_handled(self):
        """bpm=0 is not None so it IS processed (falsy-zero handled via 'is not None' guard)."""
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 0})
        hr = wm.biometric_state.heart_rate
        assert hr.bpm == 0
        assert hr.zone == "rest"
        # 0 < hr_low=45 with prev_bpm is None → hr_low event
        assert "hr_low" in _event_types(wm)

    def test_zone_rest(self):
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 44})
        assert wm.biometric_state.heart_rate.zone == "rest"

    def test_zone_cardio(self):
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 130})
        assert wm.biometric_state.heart_rate.zone == "cardio"

    def test_zone_peak(self):
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 160})
        assert wm.biometric_state.heart_rate.zone == "peak"


# ---------------------------------------------------------------------------
# heart_rate threshold crossings
# ---------------------------------------------------------------------------


class TestHeartRateThresholds:
    """Threshold crossing detection with prev_bpm is None (first reading) and with prior value."""

    def test_first_reading_above_high_generates_hr_high(self):
        """prev_bpm is None → treated as crossing regardless of direction."""
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 130})
        types = _event_types(wm)
        assert "hr_high" in types

    def test_first_reading_below_low_generates_hr_low(self):
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 40})
        assert "hr_low" in _event_types(wm)

    def test_no_event_for_normal_first_reading(self):
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 80})
        assert _events(wm) == []

    def test_second_reading_stays_high_no_new_event(self):
        """130 → 135: already above threshold, no crossing → no event."""
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 130})
        assert len(_events(wm)) == 1
        _call(wm, "garmin", "heart_rate", {"bpm": 135})
        assert len(_events(wm)) == 1

    def test_recovery_then_spike_generates_second_event(self):
        """130 → 80 (recovery) → 125 (new spike): second crossing → second event."""
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 130})  # event 1
        _call(wm, "garmin", "heart_rate", {"bpm": 80})  # recovery, no event
        _call(wm, "garmin", "heart_rate", {"bpm": 125})  # event 2
        assert len(_events(wm)) == 2
        assert all(e.event_type == "hr_high" for e in _events(wm))

    def test_stays_low_no_new_event(self):
        """40 → 35: already below low threshold, no new event."""
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 40})
        assert len(_events(wm)) == 1
        _call(wm, "garmin", "heart_rate", {"bpm": 35})
        assert len(_events(wm)) == 1

    def test_normal_to_high_crossing_generates_event(self):
        """80 → 125: crosses hr_high=120 boundary."""
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 80})
        assert _events(wm) == []
        _call(wm, "garmin", "heart_rate", {"bpm": 125})
        assert "hr_high" in _event_types(wm)

    def test_normal_to_low_crossing_generates_event(self):
        """80 → 40: crosses hr_low=45 boundary."""
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 80})
        assert _events(wm) == []
        _call(wm, "garmin", "heart_rate", {"bpm": 40})
        assert "hr_low" in _event_types(wm)

    def test_hr_high_event_has_severity_1(self):
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 130})
        ev = _events(wm)[0]
        assert ev.severity == 1
        assert ev.data.get("bpm") == 130.0

    def test_hr_low_event_has_severity_1(self):
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 40})
        ev = _events(wm)[0]
        assert ev.severity == 1

    def test_exactly_at_hr_high_boundary_no_event(self):
        """bpm == hr_high (120) does not cross; only strictly > triggers."""
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 120})
        assert _events(wm) == []

    def test_exactly_at_hr_low_boundary_no_event(self):
        """bpm == hr_low (45) does not cross; only strictly < triggers."""
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 45})
        assert _events(wm) == []


# ---------------------------------------------------------------------------
# spo2 metric
# ---------------------------------------------------------------------------


class TestSpO2Update:
    """Normal updates, threshold crossing, falsy-zero, and no-key guard."""

    def test_normal_spo2_updates_fields(self):
        wm = _wm()
        _call(wm, "garmin", "spo2", {"percent": 98})
        spo2 = wm.biometric_state.spo2
        assert spo2.percent == 98
        assert spo2.last_update > 0

    def test_bridge_connected_set_on_spo2(self):
        wm = _wm()
        _call(wm, "garmin", "spo2", {"percent": 98})
        assert wm.biometric_state.bridge_connected is True

    def test_spo2_history_recorded(self):
        wm = _wm()
        _call(wm, "garmin", "spo2", {"percent": 98})
        history = wm.biometric_state.history.get("spo2")
        assert history and history[0][1] == 98.0

    def test_missing_percent_key_is_noop(self):
        wm = _wm()
        _call(wm, "garmin", "spo2", {})
        assert wm.biometric_state.spo2.percent is None
        assert _events(wm) == []

    def test_zero_spo2_is_processed_not_skipped(self):
        """percent=0 is not None → processed; crosses spo2_low=92 → event."""
        wm = _wm()
        _call(wm, "garmin", "spo2", {"percent": 0})
        assert wm.biometric_state.spo2.percent == 0
        assert "spo2_low" in _event_types(wm)

    def test_first_reading_below_threshold_generates_event(self):
        wm = _wm()
        _call(wm, "garmin", "spo2", {"percent": 88})
        types = _event_types(wm)
        assert "spo2_low" in types
        assert _events(wm)[0].severity == 2

    def test_repeated_low_spo2_no_new_event(self):
        """88 → 85: both below threshold, no new event on second reading."""
        wm = _wm()
        _call(wm, "garmin", "spo2", {"percent": 88})
        assert len(_events(wm)) == 1
        _call(wm, "garmin", "spo2", {"percent": 85})
        assert len(_events(wm)) == 1

    def test_recovery_then_drop_generates_second_event(self):
        """88 (event) → 95 (recovery) → 90 (new drop) → second event."""
        wm = _wm()
        _call(wm, "garmin", "spo2", {"percent": 88})
        assert len(_events(wm)) == 1
        _call(wm, "garmin", "spo2", {"percent": 95})
        assert len(_events(wm)) == 1
        _call(wm, "garmin", "spo2", {"percent": 90})
        assert len(_events(wm)) == 2

    def test_normal_spo2_no_event(self):
        wm = _wm()
        _call(wm, "garmin", "spo2", {"percent": 98})
        assert _events(wm) == []

    def test_exactly_at_spo2_threshold_no_event(self):
        """percent == spo2_low (92): not strictly <, no event."""
        wm = _wm()
        _call(wm, "garmin", "spo2", {"percent": 92})
        assert _events(wm) == []


# ---------------------------------------------------------------------------
# sleep metric
# ---------------------------------------------------------------------------


class TestSleepUpdate:
    """All fields, partial payloads, and history recording."""

    def test_full_sleep_payload_updates_all_fields(self):
        wm = _wm()
        _call(
            wm,
            "garmin",
            "sleep",
            {
                "stage": "deep",
                "duration_minutes": 420,
                "deep_minutes": 90,
                "rem_minutes": 100,
                "light_minutes": 230,
                "quality_score": 82,
                "sleep_start_ts": 1708380000.0,
                "sleep_end_ts": 1708405200.0,
            },
        )
        sl = wm.biometric_state.sleep
        assert sl.stage == "deep"
        assert sl.duration_minutes == 420
        assert sl.deep_minutes == 90
        assert sl.rem_minutes == 100
        assert sl.light_minutes == 230
        assert sl.quality_score == 82
        assert sl.sleep_start_ts == 1708380000.0
        assert sl.sleep_end_ts == 1708405200.0
        assert sl.last_update > 0

    def test_bridge_connected_set_on_sleep(self):
        wm = _wm()
        _call(wm, "garmin", "sleep", {"stage": "light"})
        assert wm.biometric_state.bridge_connected is True

    def test_sleep_duration_history_recorded(self):
        wm = _wm()
        _call(wm, "garmin", "sleep", {"duration_minutes": 400})
        history = wm.biometric_state.history.get("sleep_duration")
        assert history and history[0][1] == 400.0

    def test_sleep_quality_history_recorded(self):
        wm = _wm()
        _call(wm, "garmin", "sleep", {"quality_score": 75})
        history = wm.biometric_state.history.get("sleep_quality")
        assert history and history[0][1] == 75.0

    def test_partial_sleep_payload_only_present_fields_updated(self):
        """Fields absent from payload should not touch existing state."""
        wm = _wm()
        wm.biometric_state.sleep.deep_minutes = 99  # pre-existing
        _call(wm, "garmin", "sleep", {"stage": "rem", "duration_minutes": 300})
        sl = wm.biometric_state.sleep
        assert sl.stage == "rem"
        assert sl.duration_minutes == 300
        assert sl.deep_minutes == 99  # untouched

    def test_sleep_generates_no_threshold_events(self):
        """Sleep updates must not generate threshold events."""
        wm = _wm()
        _call(wm, "garmin", "sleep", {"duration_minutes": 0, "quality_score": 0})
        assert _events(wm) == []


# ---------------------------------------------------------------------------
# activity metric
# ---------------------------------------------------------------------------


class TestActivityUpdate:
    """Steps, calories, active_minutes, level, steps_goal, history."""

    def test_full_activity_payload_updates_all_fields(self):
        wm = _wm()
        _call(
            wm,
            "garmin",
            "activity",
            {
                "steps": 5000,
                "steps_goal": 10000,
                "calories": 250,
                "active_minutes": 30,
                "level": "moderate",
            },
        )
        act = wm.biometric_state.activity
        assert act.steps == 5000
        assert act.steps_goal == 10000
        assert act.calories == 250
        assert act.active_minutes == 30
        assert act.level == "moderate"
        assert act.last_update > 0

    def test_bridge_connected_set_on_activity(self):
        wm = _wm()
        _call(wm, "garmin", "activity", {"steps": 1000})
        assert wm.biometric_state.bridge_connected is True

    def test_steps_history_recorded(self):
        wm = _wm()
        _call(wm, "garmin", "activity", {"steps": 7500})
        history = wm.biometric_state.history.get("steps")
        assert history and history[0][1] == 7500.0

    def test_partial_activity_payload(self):
        """Only present keys are updated."""
        wm = _wm()
        wm.biometric_state.activity.calories = 99
        _call(wm, "garmin", "activity", {"steps": 3000})
        act = wm.biometric_state.activity
        assert act.steps == 3000
        assert act.calories == 99  # untouched

    def test_activity_generates_no_threshold_events(self):
        wm = _wm()
        _call(wm, "garmin", "activity", {"steps": 0, "calories": 0})
        assert _events(wm) == []


# ---------------------------------------------------------------------------
# stress metric
# ---------------------------------------------------------------------------


class TestStressUpdate:
    """Category classification, threshold crossing, falsy-zero, missing key."""

    def test_normal_stress_updates_fields(self):
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 45})
        st = wm.biometric_state.stress
        assert st.level == 45
        assert st.category == "normal"
        assert st.last_update > 0

    def test_bridge_connected_set_on_stress(self):
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 45})
        assert wm.biometric_state.bridge_connected is True

    def test_stress_history_recorded(self):
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 45})
        history = wm.biometric_state.history.get("stress")
        assert history and history[0][1] == 45.0

    def test_missing_level_key_is_noop(self):
        """StressData.level defaults to 0 (int), not None.  An empty payload must
        leave the default intact and produce no events."""
        wm = _wm()
        _call(wm, "garmin", "stress", {})
        # level is not updated → stays at its dataclass default (0)
        assert wm.biometric_state.stress.level == 0
        assert wm.biometric_state.stress.last_update == 0  # no update timestamp set
        assert _events(wm) == []

    def test_zero_stress_is_processed_not_skipped(self):
        """level=0 is not None so it IS processed (falsy-zero 'is not None' guard)."""
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 0})
        assert wm.biometric_state.stress.level == 0
        assert wm.biometric_state.stress.category == "relaxed"
        # 0 <= stress_high=80, prev is None → no stress_high event
        assert _events(wm) == []

    def test_category_relaxed(self):
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 10})
        assert wm.biometric_state.stress.category == "relaxed"

    def test_category_moderate(self):
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 60})
        assert wm.biometric_state.stress.category == "moderate"

    def test_category_high(self):
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 85})
        assert wm.biometric_state.stress.category == "high"

    def test_first_reading_above_high_generates_stress_high(self):
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 90})
        assert "stress_high" in _event_types(wm)
        assert _events(wm)[0].severity == 1

    def test_repeated_high_stress_no_new_event(self):
        """90 → 95: already above threshold, no new crossing."""
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 90})
        assert len(_events(wm)) == 1
        _call(wm, "garmin", "stress", {"level": 95})
        assert len(_events(wm)) == 1

    def test_recovery_then_spike_generates_second_event(self):
        """90 → 40 (recovery) → 85 (new crossing) → second event."""
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 90})
        _call(wm, "garmin", "stress", {"level": 40})
        _call(wm, "garmin", "stress", {"level": 85})
        assert len(_events(wm)) == 2

    def test_normal_stress_no_event(self):
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 50})
        assert _events(wm) == []

    def test_exactly_at_stress_high_boundary_no_event(self):
        """level == stress_high (80): not strictly >, no event."""
        wm = _wm()
        _call(wm, "garmin", "stress", {"level": 80})
        assert _events(wm) == []


# ---------------------------------------------------------------------------
# fatigue metric
# ---------------------------------------------------------------------------


class TestFatigueUpdate:
    """score, factors, history."""

    def test_full_fatigue_payload_updates_fields(self):
        wm = _wm()
        _call(wm, "garmin", "fatigue", {"score": 35, "factors": ["high_hr"]})
        fa = wm.biometric_state.fatigue
        assert fa.score == 35
        assert fa.factors == ["high_hr"]
        assert fa.last_update > 0

    def test_bridge_connected_set_on_fatigue(self):
        wm = _wm()
        _call(wm, "garmin", "fatigue", {"score": 35})
        assert wm.biometric_state.bridge_connected is True

    def test_fatigue_history_recorded(self):
        wm = _wm()
        _call(wm, "garmin", "fatigue", {"score": 40})
        history = wm.biometric_state.history.get("fatigue")
        assert history and history[0][1] == 40.0

    def test_missing_score_key_no_update(self):
        """Payload without 'score' must leave score unchanged."""
        wm = _wm()
        wm.biometric_state.fatigue.score = 50
        _call(wm, "garmin", "fatigue", {"factors": ["sleep_debt"]})
        assert wm.biometric_state.fatigue.score == 50

    def test_fatigue_generates_no_threshold_events(self):
        wm = _wm()
        _call(wm, "garmin", "fatigue", {"score": 100})
        assert _events(wm) == []


# ---------------------------------------------------------------------------
# hrv metric
# ---------------------------------------------------------------------------


class TestHRVUpdate:
    """rmssd_ms, threshold crossing (hrv_low), falsy-zero, missing key."""

    def test_hrv_update_sets_fields(self):
        wm = _wm()
        _call(wm, "garmin", "hrv", {"rmssd_ms": 45})
        hrv = wm.biometric_state.hrv
        assert hrv.rmssd_ms == 45
        assert hrv.last_update > 0

    def test_bridge_connected_set_on_hrv(self):
        wm = _wm()
        _call(wm, "garmin", "hrv", {"rmssd_ms": 45})
        assert wm.biometric_state.bridge_connected is True

    def test_hrv_history_recorded(self):
        wm = _wm()
        _call(wm, "garmin", "hrv", {"rmssd_ms": 45})
        history = wm.biometric_state.history.get("hrv")
        assert history and history[0][1] == 45.0

    def test_missing_rmssd_key_is_noop(self):
        wm = _wm()
        _call(wm, "garmin", "hrv", {})
        assert wm.biometric_state.hrv.rmssd_ms is None
        assert _events(wm) == []

    def test_zero_rmssd_is_processed_not_skipped(self):
        """rmssd_ms=0 is not None → processed; 0 < hrv_low=20 → hrv_low event."""
        wm = _wm()
        _call(wm, "garmin", "hrv", {"rmssd_ms": 0})
        assert wm.biometric_state.hrv.rmssd_ms == 0
        assert "hrv_low" in _event_types(wm)

    def test_first_reading_below_hrv_low_generates_event(self):
        """prev_rmssd is None → treated as crossing; 15 < hrv_low=20 → event."""
        wm = _wm()
        _call(wm, "garmin", "hrv", {"rmssd_ms": 15})
        assert "hrv_low" in _event_types(wm)
        ev = _events(wm)[0]
        assert ev.severity == 1
        assert ev.data.get("rmssd_ms") == 15

    def test_repeated_low_hrv_no_new_event(self):
        """15 → 10: already below threshold, no new event."""
        wm = _wm()
        _call(wm, "garmin", "hrv", {"rmssd_ms": 15})
        assert len(_events(wm)) == 1
        _call(wm, "garmin", "hrv", {"rmssd_ms": 10})
        assert len(_events(wm)) == 1

    def test_recovery_then_drop_generates_second_event(self):
        """15 → 30 (recovery) → 12 (new drop) → second event."""
        wm = _wm()
        _call(wm, "garmin", "hrv", {"rmssd_ms": 15})
        _call(wm, "garmin", "hrv", {"rmssd_ms": 30})
        _call(wm, "garmin", "hrv", {"rmssd_ms": 12})
        assert len(_events(wm)) == 2

    def test_high_hrv_no_event(self):
        wm = _wm()
        _call(wm, "garmin", "hrv", {"rmssd_ms": 50})
        assert _events(wm) == []

    def test_exactly_at_hrv_low_boundary_no_event(self):
        """rmssd_ms == hrv_low (20): not strictly <, no event."""
        wm = _wm()
        _call(wm, "garmin", "hrv", {"rmssd_ms": 20})
        assert _events(wm) == []

    def test_prev_rmssd_at_threshold_crossing(self):
        """prev == hrv_low (20) and new < 20 → crossing → event."""
        wm = _wm()
        _call(wm, "garmin", "hrv", {"rmssd_ms": 20})  # prev=None → no event (not < 20)
        assert _events(wm) == []
        _call(wm, "garmin", "hrv", {"rmssd_ms": 19})  # 19 < 20 and prev(20) >= 20 → event
        assert "hrv_low" in _event_types(wm)


# ---------------------------------------------------------------------------
# body_temperature metric
# ---------------------------------------------------------------------------


class TestBodyTemperatureUpdate:
    """celsius, threshold crossing (body_temp_high=37.5), falsy-zero, missing key."""

    def test_body_temp_update_sets_fields(self):
        wm = _wm()
        _call(wm, "garmin", "body_temperature", {"celsius": 36.5})
        bt = wm.biometric_state.body_temperature
        assert bt.celsius == 36.5
        assert bt.last_update > 0

    def test_bridge_connected_set_on_body_temperature(self):
        wm = _wm()
        _call(wm, "garmin", "body_temperature", {"celsius": 36.5})
        assert wm.biometric_state.bridge_connected is True

    def test_body_temp_history_recorded(self):
        wm = _wm()
        _call(wm, "garmin", "body_temperature", {"celsius": 36.5})
        history = wm.biometric_state.history.get("body_temperature")
        assert history and abs(history[0][1] - 36.5) < 0.001

    def test_missing_celsius_key_is_noop(self):
        wm = _wm()
        _call(wm, "garmin", "body_temperature", {})
        assert wm.biometric_state.body_temperature.celsius is None
        assert _events(wm) == []

    def test_zero_celsius_is_processed_not_skipped(self):
        """celsius=0 is not None → processed; 0 <= body_temp_high → no event."""
        wm = _wm()
        _call(wm, "garmin", "body_temperature", {"celsius": 0})
        assert wm.biometric_state.body_temperature.celsius == 0.0
        assert _events(wm) == []

    def test_first_reading_above_body_temp_high_generates_event(self):
        """prev_temp is None → treated as crossing; 38.0 > 37.5 → event."""
        wm = _wm()
        _call(wm, "garmin", "body_temperature", {"celsius": 38.0})
        assert "body_temp_high" in _event_types(wm)
        ev = _events(wm)[0]
        assert ev.severity == 1
        assert abs(ev.data.get("celsius") - 38.0) < 0.001

    def test_repeated_high_body_temp_no_new_event(self):
        """38.0 → 38.5: already above threshold, no new event."""
        wm = _wm()
        _call(wm, "garmin", "body_temperature", {"celsius": 38.0})
        assert len(_events(wm)) == 1
        _call(wm, "garmin", "body_temperature", {"celsius": 38.5})
        assert len(_events(wm)) == 1

    def test_recovery_then_spike_generates_second_event(self):
        """38.0 → 36.0 (recovery) → 38.2 (new spike) → second event."""
        wm = _wm()
        _call(wm, "garmin", "body_temperature", {"celsius": 38.0})
        _call(wm, "garmin", "body_temperature", {"celsius": 36.0})
        _call(wm, "garmin", "body_temperature", {"celsius": 38.2})
        assert len(_events(wm)) == 2

    def test_normal_body_temp_no_event(self):
        wm = _wm()
        _call(wm, "garmin", "body_temperature", {"celsius": 36.5})
        assert _events(wm) == []

    def test_exactly_at_body_temp_boundary_no_event(self):
        """celsius == body_temp_high (37.5): not strictly >, no event."""
        wm = _wm()
        _call(wm, "garmin", "body_temperature", {"celsius": 37.5})
        assert _events(wm) == []

    def test_prev_at_threshold_then_crosses(self):
        """prev == 37.5 and new 37.6 > 37.5 → crossing → event."""
        wm = _wm()
        _call(wm, "garmin", "body_temperature", {"celsius": 37.5})  # no event
        assert _events(wm) == []
        _call(wm, "garmin", "body_temperature", {"celsius": 37.6})  # 37.6 > 37.5 and prev(37.5) <= 37.5 → event
        assert "body_temp_high" in _event_types(wm)


# ---------------------------------------------------------------------------
# respiratory_rate metric
# ---------------------------------------------------------------------------


class TestRespiratoryRateUpdate:
    """breaths_per_minute, threshold crossing (respiratory_rate_high=25), falsy-zero, missing key."""

    def test_respiratory_rate_update_sets_fields(self):
        wm = _wm()
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 16})
        rr = wm.biometric_state.respiratory_rate
        assert rr.breaths_per_minute == 16
        assert rr.last_update > 0

    def test_bridge_connected_set_on_respiratory_rate(self):
        wm = _wm()
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 16})
        assert wm.biometric_state.bridge_connected is True

    def test_respiratory_rate_history_recorded(self):
        wm = _wm()
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 16})
        history = wm.biometric_state.history.get("respiratory_rate")
        assert history and history[0][1] == 16.0

    def test_missing_breaths_per_minute_key_is_noop(self):
        wm = _wm()
        _call(wm, "garmin", "respiratory_rate", {})
        assert wm.biometric_state.respiratory_rate.breaths_per_minute is None
        assert _events(wm) == []

    def test_zero_rate_is_processed_not_skipped(self):
        """breaths_per_minute=0 is not None → processed; 0 <= respiratory_rate_high → no event."""
        wm = _wm()
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 0})
        assert wm.biometric_state.respiratory_rate.breaths_per_minute == 0
        assert _events(wm) == []

    def test_first_reading_above_threshold_generates_event(self):
        """prev_rate is None → treated as crossing; 30 > 25 → event."""
        wm = _wm()
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 30})
        assert "respiratory_rate_high" in _event_types(wm)
        ev = _events(wm)[0]
        assert ev.severity == 1
        assert ev.data.get("breaths_per_minute") == 30

    def test_repeated_high_respiratory_rate_no_new_event(self):
        """30 → 32: already above threshold, no new event."""
        wm = _wm()
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 30})
        assert len(_events(wm)) == 1
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 32})
        assert len(_events(wm)) == 1

    def test_recovery_then_spike_generates_second_event(self):
        """30 → 15 (recovery) → 28 (new spike) → second event."""
        wm = _wm()
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 30})
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 15})
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 28})
        assert len(_events(wm)) == 2

    def test_normal_respiratory_rate_no_event(self):
        wm = _wm()
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 16})
        assert _events(wm) == []

    def test_exactly_at_respiratory_rate_boundary_no_event(self):
        """breaths == respiratory_rate_high (25): not strictly >, no event."""
        wm = _wm()
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 25})
        assert _events(wm) == []

    def test_prev_at_threshold_then_crosses(self):
        """prev == 25 and new 26 > 25 → crossing → event."""
        wm = _wm()
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 25})  # no event
        assert _events(wm) == []
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 26})  # crosses
        assert "respiratory_rate_high" in _event_types(wm)


# ---------------------------------------------------------------------------
# steps (alternative topic) metric
# ---------------------------------------------------------------------------


class TestStepsAlternativeTopic:
    """hems/personal/biometrics/{provider}/steps updates activity, not heart_rate."""

    def test_steps_via_alternative_topic_updates_activity(self):
        wm = _wm()
        _call(wm, "garmin", "steps", {"count": 5000, "daily_goal": 10000})
        act = wm.biometric_state.activity
        assert act.steps == 5000
        assert act.steps_goal == 10000
        assert act.last_update > 0

    def test_bridge_connected_set_on_steps(self):
        wm = _wm()
        _call(wm, "garmin", "steps", {"count": 1000})
        assert wm.biometric_state.bridge_connected is True

    def test_steps_topic_missing_count_key_no_steps_update(self):
        wm = _wm()
        wm.biometric_state.activity.steps = 999
        _call(wm, "garmin", "steps", {"daily_goal": 10000})
        # steps not in payload → unchanged
        assert wm.biometric_state.activity.steps == 999
        # goal updated
        assert wm.biometric_state.activity.steps_goal == 10000

    def test_steps_topic_does_not_populate_heart_rate(self):
        wm = _wm()
        _call(wm, "garmin", "steps", {"count": 5000})
        assert wm.biometric_state.heart_rate.bpm is None

    def test_steps_topic_generates_no_threshold_events(self):
        wm = _wm()
        _call(wm, "garmin", "steps", {"count": 0})
        assert _events(wm) == []


# ---------------------------------------------------------------------------
# Unknown metric (graceful no-op)
# ---------------------------------------------------------------------------


class TestUnknownMetric:
    def test_unknown_metric_does_not_crash(self):
        wm = _wm()
        wm._update_biometric_state(["garmin", "unknown_metric_xyz"], {"value": 42})
        assert _events(wm) == []
        assert wm.biometric_state.bridge_connected is False


# ---------------------------------------------------------------------------
# Multi-metric state isolation
# ---------------------------------------------------------------------------


class TestMultiMetricIsolation:
    """Updating one metric must not overwrite unrelated metrics."""

    def test_heart_rate_does_not_touch_spo2(self):
        wm = _wm()
        wm.biometric_state.spo2.percent = 95
        _call(wm, "garmin", "heart_rate", {"bpm": 72})
        assert wm.biometric_state.spo2.percent == 95

    def test_spo2_does_not_touch_sleep(self):
        wm = _wm()
        wm.biometric_state.sleep.stage = "light"
        _call(wm, "garmin", "spo2", {"percent": 96})
        assert wm.biometric_state.sleep.stage == "light"

    def test_stress_does_not_touch_hrv(self):
        wm = _wm()
        wm.biometric_state.hrv.rmssd_ms = 40
        _call(wm, "garmin", "stress", {"level": 50})
        assert wm.biometric_state.hrv.rmssd_ms == 40

    def test_hrv_event_does_not_affect_heart_rate_event_count(self):
        wm = _wm()
        _call(wm, "garmin", "hrv", {"rmssd_ms": 10})  # hrv_low event
        _call(wm, "garmin", "heart_rate", {"bpm": 72})  # normal, no event
        assert len(_events(wm)) == 1
        assert _events(wm)[0].event_type == "hrv_low"

    def test_multiple_metrics_accumulate_events_independently(self):
        wm = _wm()
        _call(wm, "garmin", "heart_rate", {"bpm": 130})  # hr_high
        _call(wm, "garmin", "spo2", {"percent": 88})  # spo2_low
        _call(wm, "garmin", "stress", {"level": 90})  # stress_high
        _call(wm, "garmin", "hrv", {"rmssd_ms": 10})  # hrv_low
        _call(wm, "garmin", "body_temperature", {"celsius": 38.5})  # body_temp_high
        _call(wm, "garmin", "respiratory_rate", {"breaths_per_minute": 30})  # respiratory_rate_high
        types = set(_event_types(wm))
        assert types == {"hr_high", "spo2_low", "stress_high", "hrv_low", "body_temp_high", "respiratory_rate_high"}
