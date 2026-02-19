"""
Tests for WorldModel biometric state integration — MQTT routing, threshold events, LLM context.
"""
import time
import pytest
from world_model.data_classes import Event


class TestWorldModelBiometricRouting:
    """Test hems/personal/biometrics/{provider}/{metric} MQTT topic routing."""

    def test_heart_rate_update(self, world_model):
        """Heart rate message updates bpm, zone classification, and resting_bpm."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 72,
            "resting_bpm": 60,
        })
        hr = world_model.biometric_state.heart_rate
        assert hr.bpm == 72
        assert hr.resting_bpm == 60
        assert hr.zone == "fat_burn"  # 60 <= 72 < 120
        assert hr.last_update > 0

    def test_heart_rate_zone_rest(self, world_model):
        """BPM below 60 classifies as rest zone."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 55,
        })
        assert world_model.biometric_state.heart_rate.zone == "rest"

    def test_heart_rate_zone_cardio(self, world_model):
        """BPM 120-149 classifies as cardio zone."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 135,
        })
        assert world_model.biometric_state.heart_rate.zone == "cardio"

    def test_heart_rate_zone_peak(self, world_model):
        """BPM >= 150 classifies as peak zone."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 165,
        })
        assert world_model.biometric_state.heart_rate.zone == "peak"

    def test_spo2_update(self, world_model):
        """SpO2 message updates percent value."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/spo2", {
            "percent": 98,
        })
        spo2 = world_model.biometric_state.spo2
        assert spo2.percent == 98
        assert spo2.last_update > 0

    def test_sleep_data_update(self, world_model):
        """Sleep message updates all sleep fields."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/sleep", {
            "stage": "deep",
            "duration_minutes": 420,
            "deep_minutes": 90,
            "rem_minutes": 100,
            "light_minutes": 230,
            "quality_score": 82,
            "sleep_start_ts": 1708380000.0,
            "sleep_end_ts": 1708405200.0,
        })
        sleep = world_model.biometric_state.sleep
        assert sleep.stage == "deep"
        assert sleep.duration_minutes == 420
        assert sleep.deep_minutes == 90
        assert sleep.rem_minutes == 100
        assert sleep.light_minutes == 230
        assert sleep.quality_score == 82
        assert sleep.sleep_start_ts == 1708380000.0
        assert sleep.sleep_end_ts == 1708405200.0
        assert sleep.last_update > 0

    def test_activity_data_update(self, world_model):
        """Activity message updates steps, calories, and other fields."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/activity", {
            "steps": 5000,
            "steps_goal": 10000,
            "calories": 250,
            "active_minutes": 30,
            "level": "moderate",
        })
        act = world_model.biometric_state.activity
        assert act.steps == 5000
        assert act.steps_goal == 10000
        assert act.calories == 250
        assert act.active_minutes == 30
        assert act.level == "moderate"
        assert act.last_update > 0

    def test_stress_data_update(self, world_model):
        """Stress message updates level and auto-classifies category."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/stress", {
            "level": 45,
        })
        stress = world_model.biometric_state.stress
        assert stress.level == 45
        assert stress.category == "normal"  # 25 <= 45 < 50
        assert stress.last_update > 0

    def test_stress_category_relaxed(self, world_model):
        """Stress level < 25 classifies as relaxed."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/stress", {
            "level": 10,
        })
        assert world_model.biometric_state.stress.category == "relaxed"

    def test_stress_category_moderate(self, world_model):
        """Stress level 50-74 classifies as moderate."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/stress", {
            "level": 60,
        })
        assert world_model.biometric_state.stress.category == "moderate"

    def test_stress_category_high(self, world_model):
        """Stress level >= 75 classifies as high."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/stress", {
            "level": 85,
        })
        assert world_model.biometric_state.stress.category == "high"

    def test_fatigue_data_update(self, world_model):
        """Fatigue message updates score and factors."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/fatigue", {
            "score": 35,
            "factors": ["high_hr"],
        })
        fatigue = world_model.biometric_state.fatigue
        assert fatigue.score == 35
        assert fatigue.factors == ["high_hr"]
        assert fatigue.last_update > 0

    def test_steps_alternative_topic(self, world_model):
        """Steps via alternative topic updates activity.steps and steps_goal."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/steps", {
            "count": 5000,
            "daily_goal": 10000,
        })
        act = world_model.biometric_state.activity
        assert act.steps == 5000
        assert act.steps_goal == 10000
        assert act.last_update > 0

    def test_bridge_status_connected(self, world_model):
        """Bridge status message sets connected state and provider."""
        assert world_model.biometric_state.bridge_connected is False
        world_model.update_from_mqtt("hems/personal/biometrics/bridge/status", {
            "connected": True,
            "provider": "garmin",
        })
        bio = world_model.biometric_state
        assert bio.bridge_connected is True
        assert bio.provider == "garmin"

    def test_bridge_status_disconnected(self, world_model):
        """Bridge status disconnect clears connected flag."""
        world_model.update_from_mqtt("hems/personal/biometrics/bridge/status", {
            "connected": True,
            "provider": "garmin",
        })
        world_model.update_from_mqtt("hems/personal/biometrics/bridge/status", {
            "connected": False,
        })
        assert world_model.biometric_state.bridge_connected is False


class TestWorldModelBiometricThresholds:
    """Test event generation from biometric threshold crossings."""

    def test_hr_high_threshold_event(self, world_model):
        """Heart rate crossing > 120 generates hr_high event."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 130,
        })
        events = world_model.biometric_state.events
        assert len(events) == 1
        assert events[0].event_type == "hr_high"
        assert events[0].severity == 1

    def test_hr_low_threshold_event(self, world_model):
        """Heart rate crossing < 45 generates hr_low event."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 40,
        })
        events = world_model.biometric_state.events
        assert len(events) == 1
        assert events[0].event_type == "hr_low"
        assert events[0].severity == 1

    def test_hr_normal_no_event(self, world_model):
        """Heart rate within normal range generates no event."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 72,
        })
        assert len(world_model.biometric_state.events) == 0

    def test_spo2_low_threshold_event(self, world_model):
        """SpO2 crossing < 92 generates spo2_low event with severity 2."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/spo2", {
            "percent": 88,
        })
        events = world_model.biometric_state.events
        assert len(events) == 1
        assert events[0].event_type == "spo2_low"
        assert events[0].severity == 2

    def test_stress_high_threshold_event(self, world_model):
        """Stress crossing > 80 generates stress_high event."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/stress", {
            "level": 90,
        })
        events = world_model.biometric_state.events
        assert len(events) == 1
        assert events[0].event_type == "stress_high"
        assert events[0].severity == 1

    def test_repeated_high_hr_no_new_event(self, world_model):
        """Repeated HR above threshold (no crossing) generates no new event."""
        # First crossing: 70 → 130 (prev is None → generates event)
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 130,
        })
        assert len(world_model.biometric_state.events) == 1

        # Second update: 130 → 135 (already above threshold, no crossing)
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 135,
        })
        assert len(world_model.biometric_state.events) == 1  # No new event

    def test_repeated_low_spo2_no_new_event(self, world_model):
        """Repeated SpO2 below threshold (no crossing) generates no new event."""
        # First crossing: None → 88 (generates event)
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/spo2", {
            "percent": 88,
        })
        assert len(world_model.biometric_state.events) == 1

        # Second update: 88 → 85 (already below threshold, no crossing)
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/spo2", {
            "percent": 85,
        })
        assert len(world_model.biometric_state.events) == 1

    def test_repeated_high_stress_no_new_event(self, world_model):
        """Repeated stress above threshold (no crossing) generates no new event."""
        # First crossing: 0 → 90 (prev is 0, treated as None-like)
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/stress", {
            "level": 90,
        })
        assert len(world_model.biometric_state.events) == 1

        # Second update: 90 → 95 (already above threshold, no crossing)
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/stress", {
            "level": 95,
        })
        assert len(world_model.biometric_state.events) == 1

    def test_hr_recovery_then_spike_generates_new_event(self, world_model):
        """HR recovering to normal and spiking again generates a second event."""
        # First spike
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 130,
        })
        assert len(world_model.biometric_state.events) == 1

        # Recovery
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 80,
        })
        assert len(world_model.biometric_state.events) == 1  # No event on recovery

        # Second spike (crosses threshold again)
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 125,
        })
        assert len(world_model.biometric_state.events) == 2


class TestWorldModelBiometricLLMContext:
    """Test biometric section in LLM context."""

    def test_no_biometric_section_when_no_data(self, world_model):
        """No biometric data means no biometric section in LLM context."""
        ctx = world_model.get_llm_context()
        assert "バイオメトリクス" not in ctx

    def test_biometric_context_with_heart_rate(self, world_model):
        """Heart rate data appears in LLM context."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 72,
            "resting_bpm": 60,
        })
        ctx = world_model.get_llm_context()
        assert "### バイオメトリクス" in ctx
        assert "72bpm" in ctx
        assert "fat_burn" in ctx
        assert "安静時60bpm" in ctx

    def test_biometric_context_with_spo2(self, world_model):
        """SpO2 data appears in LLM context."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/spo2", {
            "percent": 98,
        })
        ctx = world_model.get_llm_context()
        assert "### バイオメトリクス" in ctx
        assert "SpO2" in ctx
        assert "98%" in ctx

    def test_biometric_context_with_stress(self, world_model):
        """Stress data appears in LLM context."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/stress", {
            "level": 45,
        })
        ctx = world_model.get_llm_context()
        assert "ストレス" in ctx
        assert "normal" in ctx

    def test_biometric_context_with_fatigue(self, world_model):
        """Fatigue data appears in LLM context."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/fatigue", {
            "score": 35,
            "factors": ["high_hr"],
        })
        ctx = world_model.get_llm_context()
        assert "疲労度" in ctx
        assert "35" in ctx

    def test_biometric_context_with_sleep(self, world_model):
        """Sleep data appears in LLM context."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/sleep", {
            "stage": "deep",
            "duration_minutes": 420,
            "quality_score": 82,
        })
        ctx = world_model.get_llm_context()
        assert "睡眠" in ctx
        assert "420分" in ctx
        assert "品質82" in ctx

    def test_biometric_context_with_activity(self, world_model):
        """Activity data appears in LLM context showing step progress."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/activity", {
            "steps": 5000,
            "steps_goal": 10000,
        })
        ctx = world_model.get_llm_context()
        assert "歩数" in ctx
        assert "5000" in ctx
        assert "50%" in ctx  # goal_progress

    def test_biometric_bridge_disconnected_warning(self, world_model):
        """Disconnected bridge shows warning when biometric data exists."""
        # Add some data so biometric section appears; bridge_connected defaults to False
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 72,
        })
        # bridge_connected is set to True by the heart_rate update.
        # Explicitly disconnect.
        world_model.update_from_mqtt("hems/personal/biometrics/bridge/status", {
            "connected": False,
        })
        ctx = world_model.get_llm_context()
        assert "⚠" in ctx
        assert "バイオメトリクスブリッジ" in ctx
