"""
Tests for PowerModeManager and RuleEngine.evaluate_critical().
"""
import time
from unittest.mock import patch

import pytest
from world_model.data_classes import (
    BiometricState, HeartRateData, SleepData, SpO2Data,
    ZoneState, OccupancyData, EnvironmentData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager():
    from low_power_mode import PowerModeManager
    return PowerModeManager()


def _make_engine():
    from rule_engine import RuleEngine
    engine = RuleEngine()
    engine._cooldowns = {}
    return engine


# ---------------------------------------------------------------------------
# PowerModeManager — initial state
# ---------------------------------------------------------------------------

class TestPowerModeManagerInit:
    def test_starts_in_normal_mode(self):
        mgr = _make_manager()
        assert mgr.mode == "normal"
        assert not mgr.is_low_power
        assert mgr.cycle_interval == 30
        assert mgr.min_cycle_interval == 25


# ---------------------------------------------------------------------------
# PowerModeManager — entry: sleep via biometrics
# ---------------------------------------------------------------------------

class TestPowerModeSleepBiometric:
    def test_deep_sleep_enters_sleep_mode(self, world_model):
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()

        changed = mgr.evaluate(world_model)
        assert changed
        assert mgr.mode == "sleep"
        assert mgr.is_low_power
        assert mgr.cycle_interval == 300   # 5 min default

    def test_light_sleep_enters_sleep_mode(self, world_model):
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "light"
        world_model.biometric_state.sleep.last_update = time.time()

        assert mgr.evaluate(world_model)
        assert mgr.mode == "sleep"

    def test_rem_sleep_enters_sleep_mode(self, world_model):
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "rem"
        world_model.biometric_state.sleep.last_update = time.time()

        assert mgr.evaluate(world_model)
        assert mgr.mode == "sleep"

    def test_awake_stage_does_not_enter_sleep(self, world_model):
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "awake"
        world_model.biometric_state.sleep.last_update = time.time()

        assert not mgr.evaluate(world_model)
        assert mgr.mode == "normal"

    def test_unknown_stage_does_not_enter_sleep(self, world_model):
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "unknown"

        assert not mgr.evaluate(world_model)
        assert mgr.mode == "normal"


# ---------------------------------------------------------------------------
# PowerModeManager — entry: sleep via posture (late night)
# ---------------------------------------------------------------------------

class TestPowerModeSleepPosture:
    def test_late_night_static_idle_enters_sleep(self, world_model):
        mgr = _make_manager()
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.count = 1
        zone.occupancy.last_update = time.time()
        zone.occupancy.activity_class = "idle"
        zone.occupancy.posture_status = "static"
        zone.occupancy.posture_duration_sec = 700
        world_model.zones["living_room"] = zone

        with patch("low_power_mode.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 23
            changed = mgr.evaluate(world_model)

        assert changed
        assert mgr.mode == "sleep"

    def test_not_idle_no_sleep(self, world_model):
        mgr = _make_manager()
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.count = 1
        zone.occupancy.last_update = time.time()
        zone.occupancy.activity_class = "low"        # not idle
        zone.occupancy.posture_status = "static"
        zone.occupancy.posture_duration_sec = 700
        world_model.zones["living_room"] = zone

        with patch("low_power_mode.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 23
            changed = mgr.evaluate(world_model)

        assert not changed
        assert mgr.mode == "normal"

    def test_short_posture_no_sleep(self, world_model):
        mgr = _make_manager()
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.count = 1
        zone.occupancy.last_update = time.time()
        zone.occupancy.activity_class = "idle"
        zone.occupancy.posture_status = "static"
        zone.occupancy.posture_duration_sec = 300  # < 600
        world_model.zones["living_room"] = zone

        with patch("low_power_mode.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 1
            changed = mgr.evaluate(world_model)

        assert not changed

    def test_daytime_static_idle_no_sleep(self, world_model):
        mgr = _make_manager()
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.count = 1
        zone.occupancy.last_update = time.time()
        zone.occupancy.activity_class = "idle"
        zone.occupancy.posture_status = "static"
        zone.occupancy.posture_duration_sec = 900
        world_model.zones["living_room"] = zone

        with patch("low_power_mode.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 14  # daytime — not in 23-5 window
            changed = mgr.evaluate(world_model)

        assert not changed


# ---------------------------------------------------------------------------
# PowerModeManager — entry: away mode
# ---------------------------------------------------------------------------

class TestPowerModeAway:
    def test_all_empty_for_confirm_period_enters_away(self, world_model):
        from low_power_mode import AWAY_CONFIRM_SECONDS
        mgr = _make_manager()
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.count = 0
        zone.occupancy.last_update = time.time()
        world_model.zones["living_room"] = zone

        with patch("low_power_mode.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 14

            # First call: starts confirmation timer, no mode change yet
            changed = mgr.evaluate(world_model)
            assert not changed
            assert mgr.mode == "normal"

            # Simulate time passing (exceed confirmation period)
            mgr._away_candidate_since -= AWAY_CONFIRM_SECONDS + 1

            changed = mgr.evaluate(world_model)

        assert changed
        assert mgr.mode == "away"
        assert mgr.cycle_interval == 600  # 10 min default

    def test_occupancy_resets_away_candidate(self, world_model):
        mgr = _make_manager()
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.count = 0
        zone.occupancy.last_update = time.time()
        world_model.zones["living_room"] = zone

        with patch("low_power_mode.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 14
            mgr.evaluate(world_model)
            assert mgr._away_candidate_since is not None

            # Someone appears
            zone.occupancy.count = 1
            mgr.evaluate(world_model)

        assert mgr._away_candidate_since is None
        assert mgr.mode == "normal"

    def test_no_zones_no_away(self, world_model):
        mgr = _make_manager()
        # world_model.zones is empty by default
        changed = mgr.evaluate(world_model)
        assert not changed


# ---------------------------------------------------------------------------
# PowerModeManager — exit: sleep → normal
# ---------------------------------------------------------------------------

class TestPowerModeExitSleep:
    def _put_in_sleep(self, world_model):
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()
        mgr.evaluate(world_model)
        assert mgr.mode == "sleep"
        return mgr

    def test_awake_stage_exits_sleep(self, world_model):
        mgr = self._put_in_sleep(world_model)
        world_model.biometric_state.sleep.stage = "awake"

        changed = mgr.evaluate(world_model)
        assert changed
        assert mgr.mode == "normal"

    def test_morning_activity_exits_sleep(self, world_model):
        mgr = self._put_in_sleep(world_model)
        # Stage still shows sleep but activity detected in morning
        world_model.biometric_state.sleep.stage = "light"
        zone = ZoneState(zone_id="bedroom")
        zone.occupancy.count = 1
        zone.occupancy.last_update = time.time()
        zone.occupancy.activity_class = "low"
        world_model.zones["bedroom"] = zone

        with patch("low_power_mode.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 7
            changed = mgr.evaluate(world_model)

        assert changed
        assert mgr.mode == "normal"

    def test_morning_idle_does_not_exit_sleep(self, world_model):
        mgr = self._put_in_sleep(world_model)
        world_model.biometric_state.sleep.stage = "deep"
        zone = ZoneState(zone_id="bedroom")
        zone.occupancy.count = 1
        zone.occupancy.last_update = time.time()
        zone.occupancy.activity_class = "idle"  # still idle
        world_model.zones["bedroom"] = zone

        with patch("low_power_mode.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 7
            changed = mgr.evaluate(world_model)

        assert not changed
        assert mgr.mode == "sleep"


# ---------------------------------------------------------------------------
# PowerModeManager — exit: away → normal
# ---------------------------------------------------------------------------

class TestPowerModeExitAway:
    def _put_in_away(self, world_model):
        from low_power_mode import AWAY_CONFIRM_SECONDS
        mgr = _make_manager()
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.count = 0
        zone.occupancy.last_update = time.time()
        world_model.zones["living_room"] = zone

        with patch("low_power_mode.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 14
            mgr.evaluate(world_model)
            mgr._away_candidate_since -= AWAY_CONFIRM_SECONDS + 1
            mgr.evaluate(world_model)

        assert mgr.mode == "away"
        return mgr

    def test_occupancy_returns_exits_away(self, world_model):
        mgr = self._put_in_away(world_model)
        world_model.zones["living_room"].occupancy.count = 1

        changed = mgr.evaluate(world_model)
        assert changed
        assert mgr.mode == "normal"

    def test_fresh_biometrics_exits_away(self, world_model):
        mgr = self._put_in_away(world_model)
        world_model.biometric_state.heart_rate.bpm = 70
        world_model.biometric_state.heart_rate.last_update = time.time()

        changed = mgr.evaluate(world_model)
        assert changed
        assert mgr.mode == "normal"

    def test_stale_biometrics_does_not_exit(self, world_model):
        mgr = self._put_in_away(world_model)
        world_model.biometric_state.heart_rate.bpm = 70
        world_model.biometric_state.heart_rate.last_update = time.time() - 200  # old

        changed = mgr.evaluate(world_model)
        assert not changed
        assert mgr.mode == "away"


# ---------------------------------------------------------------------------
# RuleEngine.evaluate_critical — CO2 danger
# ---------------------------------------------------------------------------

class TestEvaluateCriticalCO2:
    def test_co2_above_critical_fires(self, world_model):
        engine = _make_engine()
        zone = ZoneState(zone_id="living_room")
        zone.environment.co2 = 1600  # above CO2_CRITICAL (1500)
        world_model.zones["living_room"] = zone

        actions = engine.evaluate_critical(world_model)
        task_actions = [a for a in actions if a["tool"] == "create_task"]
        speak_actions = [a for a in actions if a["tool"] == "speak"]

        assert len(task_actions) == 1
        assert task_actions[0]["args"]["urgency"] == 5
        assert len(speak_actions) == 1
        assert speak_actions[0]["args"]["tone"] == "urgent"

    def test_co2_below_critical_silent(self, world_model):
        engine = _make_engine()
        zone = ZoneState(zone_id="living_room")
        zone.environment.co2 = 1200  # high but below critical
        world_model.zones["living_room"] = zone

        actions = engine.evaluate_critical(world_model)
        assert len(actions) == 0

    def test_co2_critical_cooldown_respected(self, world_model):
        engine = _make_engine()
        zone = ZoneState(zone_id="living_room")
        zone.environment.co2 = 1600
        world_model.zones["living_room"] = zone

        engine.evaluate_critical(world_model)
        actions = engine.evaluate_critical(world_model)
        task_actions = [a for a in actions if a["tool"] == "create_task"]
        assert len(task_actions) == 0  # cooldown prevents second fire


# ---------------------------------------------------------------------------
# RuleEngine.evaluate_critical — extreme temperature
# ---------------------------------------------------------------------------

class TestEvaluateCriticalTemperature:
    def test_extreme_heat_fires(self, world_model):
        engine = _make_engine()
        zone = ZoneState(zone_id="living_room")
        zone.environment.temperature = 41.0  # above TEMP_CRITICAL_HIGH (40)
        world_model.zones["living_room"] = zone

        actions = engine.evaluate_critical(world_model)
        speaks = [a for a in actions if a["tool"] == "speak"]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "urgent"
        assert "熱中症" in speaks[0]["args"]["message"]

    def test_extreme_cold_fires(self, world_model):
        engine = _make_engine()
        zone = ZoneState(zone_id="living_room")
        zone.environment.temperature = 3.0  # below TEMP_CRITICAL_LOW (5)
        world_model.zones["living_room"] = zone

        actions = engine.evaluate_critical(world_model)
        speaks = [a for a in actions if a["tool"] == "speak"]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "urgent"

    def test_normal_temperature_silent(self, world_model):
        engine = _make_engine()
        zone = ZoneState(zone_id="living_room")
        zone.environment.temperature = 25.0
        world_model.zones["living_room"] = zone

        actions = engine.evaluate_critical(world_model)
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# RuleEngine.evaluate_critical — SpO2 critical
# ---------------------------------------------------------------------------

class TestEvaluateCriticalSpO2:
    def test_critical_spo2_fires(self, world_model):
        engine = _make_engine()
        world_model.biometric_state.spo2.percent = 85  # below SPO2_CRITICAL_LOW (88)
        world_model.biometric_state.spo2.last_update = time.time()

        actions = engine.evaluate_critical(world_model)
        speaks = [a for a in actions if a["tool"] == "speak"]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "urgent"
        assert "85" in speaks[0]["args"]["message"]

    def test_stale_spo2_silent(self, world_model):
        engine = _make_engine()
        world_model.biometric_state.spo2.percent = 85
        world_model.biometric_state.spo2.last_update = time.time() - 400  # older than 300s

        actions = engine.evaluate_critical(world_model)
        assert len(actions) == 0

    def test_normal_spo2_silent(self, world_model):
        engine = _make_engine()
        world_model.biometric_state.spo2.percent = 97
        world_model.biometric_state.spo2.last_update = time.time()

        actions = engine.evaluate_critical(world_model)
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# RuleEngine.evaluate_critical — high HR during sleep
# ---------------------------------------------------------------------------

class TestEvaluateCriticalHRSleep:
    def test_high_hr_during_sleep_fires(self, world_model):
        engine = _make_engine()
        world_model.biometric_state.heart_rate.bpm = 160  # above HR_CRITICAL_SLEEP (150)
        world_model.biometric_state.heart_rate.last_update = time.time()
        world_model.biometric_state.sleep.stage = "deep"

        actions = engine.evaluate_critical(world_model)
        speaks = [a for a in actions if a["tool"] == "speak"]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "urgent"

    def test_high_hr_while_awake_silent(self, world_model):
        engine = _make_engine()
        world_model.biometric_state.heart_rate.bpm = 160
        world_model.biometric_state.heart_rate.last_update = time.time()
        world_model.biometric_state.sleep.stage = "awake"

        actions = engine.evaluate_critical(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "心拍数" in a["args"].get("message", "")]
        assert len(speaks) == 0

    def test_normal_hr_during_sleep_silent(self, world_model):
        engine = _make_engine()
        world_model.biometric_state.heart_rate.bpm = 60
        world_model.biometric_state.heart_rate.last_update = time.time()
        world_model.biometric_state.sleep.stage = "deep"

        actions = engine.evaluate_critical(world_model)
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# PowerModeManager — LLM call throttling
# ---------------------------------------------------------------------------

class TestLLMCallThrottling:
    def test_allow_llm_in_normal_mode(self):
        mgr = _make_manager()
        assert mgr.mode == "normal"
        assert mgr.allow_llm_call()

    def test_allow_llm_first_call_in_low_power(self, world_model):
        from low_power_mode import LOW_POWER_LLM_COOLDOWN
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()
        mgr.evaluate(world_model)
        assert mgr.is_low_power

        # No LLM calls yet → should be allowed
        assert mgr.allow_llm_call()

    def test_block_llm_after_record(self, world_model):
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()
        mgr.evaluate(world_model)

        mgr.record_llm_call()
        assert not mgr.allow_llm_call()

    def test_allow_llm_after_cooldown(self, world_model):
        from low_power_mode import LOW_POWER_LLM_COOLDOWN
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()
        mgr.evaluate(world_model)

        now = time.time()
        mgr.record_llm_call(now=now)
        # Simulate cooldown elapsed
        future = now + LOW_POWER_LLM_COOLDOWN + 1
        assert mgr.allow_llm_call(now=future)

    def test_seconds_until_llm_allowed_zero_when_fresh(self):
        mgr = _make_manager()
        assert mgr.seconds_until_llm_allowed() == 0

    def test_seconds_until_llm_allowed_nonzero_after_call(self, world_model):
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()
        mgr.evaluate(world_model)

        mgr.record_llm_call()
        remaining = mgr.seconds_until_llm_allowed()
        assert remaining > 0

    def test_get_status_includes_llm_cooldown(self, world_model):
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()
        mgr.evaluate(world_model)

        mgr.record_llm_call()
        status = mgr.get_status()
        assert "llm_cooldown_remaining_sec" in status
        assert status["llm_cooldown_remaining_sec"] > 0

    def test_no_throttle_in_normal_mode_after_low_power_exit(self, world_model):
        """LLM throttle should not affect normal mode even after low-power period."""
        mgr = _make_manager()
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()
        mgr.evaluate(world_model)

        mgr.record_llm_call()
        assert not mgr.allow_llm_call()  # blocked in low-power

        # Return to normal
        world_model.biometric_state.sleep.stage = "awake"
        mgr.evaluate(world_model)
        assert mgr.mode == "normal"
        assert mgr.allow_llm_call()  # always allowed in normal mode
