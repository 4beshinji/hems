"""
Tests for extended tracking features:
- SensorFusion add_reading/get_value (bug fix)
- New biometric fields (HRV, body temperature, respiratory rate)
- New data classes (HRVData, BodyTemperatureData, RespiratoryRateData, ScreenTimeData)
- World model MQTT handlers for new biometric topics
- New rule engine rules (humidity, pressure, screen time, HRV, body temp, respiratory rate)
- Schedule learner persistence
"""
import time
import json
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest


# ===== SensorFusion Bug Fix =====


class TestSensorFusionAddReading:
    """Test that SensorFusion.add_reading and get_value work correctly."""

    def test_add_reading_and_get_value(self):
        from world_model.sensor_fusion import SensorFusion
        f = SensorFusion()
        f.add_reading(25.0)
        val = f.get_value()
        assert val is not None
        assert abs(val - 25.0) < 0.1

    def test_multiple_readings_fused(self):
        from world_model.sensor_fusion import SensorFusion
        f = SensorFusion()
        f.add_reading(20.0)
        f.add_reading(22.0)
        f.add_reading(21.0)
        val = f.get_value()
        assert val is not None
        # Fused value should be close to average (weighted by recency)
        assert 19.0 < val < 23.0

    def test_get_value_no_readings_returns_none(self):
        from world_model.sensor_fusion import SensorFusion
        f = SensorFusion()
        assert f.get_value() is None

    def test_max_readings_pruned(self):
        from world_model.sensor_fusion import SensorFusion
        f = SensorFusion()
        for i in range(20):
            f.add_reading(float(i))
        assert len(f._readings) == f._max_readings

    def test_world_model_sensor_update_uses_fusion(self, world_model):
        """WorldModel._update_sensor calls add_reading/get_value without error."""
        world_model.update_from_mqtt("office/living_room/sensor/env1/temperature", {
            "temperature": 25.5,
        })
        zone = world_model.get_zone("living_room")
        assert zone is not None
        assert zone.environment.temperature == 25.5


# ===== New Data Classes =====


class TestHRVData:
    def test_defaults(self):
        from world_model.data_classes import HRVData
        h = HRVData()
        assert h.rmssd_ms is None
        assert h.last_update == 0

    def test_custom_values(self):
        from world_model.data_classes import HRVData
        h = HRVData(rmssd_ms=45, last_update=100.0)
        assert h.rmssd_ms == 45
        assert h.last_update == 100.0


class TestBodyTemperatureData:
    def test_defaults(self):
        from world_model.data_classes import BodyTemperatureData
        b = BodyTemperatureData()
        assert b.celsius is None
        assert b.last_update == 0

    def test_custom_values(self):
        from world_model.data_classes import BodyTemperatureData
        b = BodyTemperatureData(celsius=36.5, last_update=200.0)
        assert b.celsius == 36.5


class TestRespiratoryRateData:
    def test_defaults(self):
        from world_model.data_classes import RespiratoryRateData
        r = RespiratoryRateData()
        assert r.breaths_per_minute is None
        assert r.last_update == 0

    def test_custom_values(self):
        from world_model.data_classes import RespiratoryRateData
        r = RespiratoryRateData(breaths_per_minute=16, last_update=300.0)
        assert r.breaths_per_minute == 16


class TestScreenTimeData:
    def test_defaults(self):
        from world_model.data_classes import ScreenTimeData
        s = ScreenTimeData()
        assert s.total_minutes == 0
        assert s.active_app == ""
        assert s.session_start_ts == 0
        assert s.last_update == 0


class TestBiometricStateNewFields:
    """Test new fields in BiometricState."""

    def test_has_hrv_field(self):
        from world_model.data_classes import BiometricState, HRVData
        bs = BiometricState()
        assert isinstance(bs.hrv, HRVData)

    def test_has_body_temperature_field(self):
        from world_model.data_classes import BiometricState, BodyTemperatureData
        bs = BiometricState()
        assert isinstance(bs.body_temperature, BodyTemperatureData)

    def test_has_respiratory_rate_field(self):
        from world_model.data_classes import BiometricState, RespiratoryRateData
        bs = BiometricState()
        assert isinstance(bs.respiratory_rate, RespiratoryRateData)

    def test_last_update_includes_new_fields(self):
        from world_model.data_classes import BiometricState
        bs = BiometricState()
        bs.hrv.last_update = 500.0
        assert bs.last_update == 500.0

        bs.body_temperature.last_update = 600.0
        assert bs.last_update == 600.0

        bs.respiratory_rate.last_update = 700.0
        assert bs.last_update == 700.0


class TestUserStateScreenTime:
    def test_has_screen_time_field(self):
        from world_model.data_classes import UserState, ScreenTimeData
        us = UserState()
        assert isinstance(us.screen_time, ScreenTimeData)


# ===== World Model MQTT Handlers =====


class TestWorldModelHRVRouting:
    def test_hrv_update(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/hrv", {
            "rmssd_ms": 42,
        })
        hrv = world_model.biometric_state.hrv
        assert hrv.rmssd_ms == 42
        assert hrv.last_update > 0
        assert world_model.biometric_state.bridge_connected is True

    def test_hrv_low_threshold_event(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/hrv", {
            "rmssd_ms": 15,
        })
        events = world_model.biometric_state.events
        assert len(events) == 1
        assert events[0].event_type == "hrv_low"
        assert events[0].severity == 1

    def test_hrv_normal_no_event(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/hrv", {
            "rmssd_ms": 50,
        })
        assert len(world_model.biometric_state.events) == 0

    def test_hrv_repeated_low_no_new_event(self, world_model):
        """Repeated low HRV without crossing generates no new event."""
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/hrv", {
            "rmssd_ms": 15,
        })
        assert len(world_model.biometric_state.events) == 1
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/hrv", {
            "rmssd_ms": 12,
        })
        assert len(world_model.biometric_state.events) == 1


class TestWorldModelBodyTempRouting:
    def test_body_temp_update(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/body_temperature", {
            "celsius": 36.5,
        })
        bt = world_model.biometric_state.body_temperature
        assert bt.celsius == 36.5
        assert bt.last_update > 0

    def test_body_temp_high_threshold_event(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/body_temperature", {
            "celsius": 38.0,
        })
        events = world_model.biometric_state.events
        assert len(events) == 1
        assert events[0].event_type == "body_temp_high"

    def test_body_temp_normal_no_event(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/body_temperature", {
            "celsius": 36.5,
        })
        assert len(world_model.biometric_state.events) == 0


class TestWorldModelRespiratoryRateRouting:
    def test_respiratory_rate_update(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/respiratory_rate", {
            "breaths_per_minute": 16,
        })
        rr = world_model.biometric_state.respiratory_rate
        assert rr.breaths_per_minute == 16
        assert rr.last_update > 0

    def test_respiratory_rate_high_threshold_event(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/respiratory_rate", {
            "breaths_per_minute": 30,
        })
        events = world_model.biometric_state.events
        assert len(events) == 1
        assert events[0].event_type == "respiratory_rate_high"

    def test_respiratory_rate_normal_no_event(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/respiratory_rate", {
            "breaths_per_minute": 18,
        })
        assert len(world_model.biometric_state.events) == 0


class TestWorldModelBiometricLLMContextNewFields:
    def test_hrv_in_context(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/hrv", {
            "rmssd_ms": 42,
        })
        ctx = world_model.get_llm_context()
        assert "HRV(RMSSD)" in ctx
        assert "42ms" in ctx

    def test_body_temp_in_context(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/body_temperature", {
            "celsius": 36.8,
        })
        ctx = world_model.get_llm_context()
        assert "体温" in ctx
        assert "36.8" in ctx

    def test_respiratory_rate_in_context(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/respiratory_rate", {
            "breaths_per_minute": 16,
        })
        ctx = world_model.get_llm_context()
        assert "呼吸数" in ctx
        assert "16" in ctx

    def test_screen_time_in_context(self, world_model):
        world_model.user.screen_time.total_minutes = 150
        ctx = world_model.get_llm_context()
        assert "スクリーンタイム" in ctx
        assert "2h30m" in ctx


# ===== Rule Engine New Rules =====


class TestRuleEngineHumidityRules:
    def _make_engine(self):
        from rule_engine import RuleEngine
        engine = RuleEngine()
        engine._cooldowns = {}
        return engine

    def test_humidity_high_triggers_speak(self, world_model):
        engine = self._make_engine()
        zone = world_model._get_zone("living_room")
        zone.environment.humidity = 75

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "湿度" in a["args"]["message"]]
        assert len(speaks) == 1
        assert "75" in speaks[0]["args"]["message"]
        assert "除湿" in speaks[0]["args"]["message"]

    def test_humidity_low_triggers_speak(self, world_model):
        engine = self._make_engine()
        zone = world_model._get_zone("living_room")
        zone.environment.humidity = 25

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "湿度" in a["args"]["message"]]
        assert len(speaks) == 1
        assert "25" in speaks[0]["args"]["message"]
        assert "加湿" in speaks[0]["args"]["message"]

    def test_humidity_normal_no_action(self, world_model):
        engine = self._make_engine()
        zone = world_model._get_zone("living_room")
        zone.environment.humidity = 50

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "湿度" in a["args"]["message"]]
        assert len(speaks) == 0


class TestRuleEnginePressureDropRule:
    def _make_engine(self):
        from rule_engine import RuleEngine
        engine = RuleEngine()
        engine._cooldowns = {}
        engine._pressure_history = {}
        return engine

    def test_pressure_drop_triggers_speak(self, world_model):
        engine = self._make_engine()
        zone = world_model._get_zone("living_room")

        # First reading establishes baseline
        zone.environment.pressure = 1013.0
        engine.evaluate(world_model)

        # Second reading with significant drop
        zone.environment.pressure = 1007.0
        engine._cooldowns = {}  # Reset cooldown
        actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "気圧" in a["args"]["message"]]
        assert len(speaks) == 1
        assert "頭痛" in speaks[0]["args"]["message"]

    def test_pressure_stable_no_action(self, world_model):
        engine = self._make_engine()
        zone = world_model._get_zone("living_room")

        zone.environment.pressure = 1013.0
        engine.evaluate(world_model)

        zone.environment.pressure = 1012.0
        engine._cooldowns = {}
        actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "気圧" in a["args"]["message"]]
        assert len(speaks) == 0


class TestRuleEngineScreenTimeRule:
    def _make_engine(self):
        from rule_engine import RuleEngine
        engine = RuleEngine()
        engine._cooldowns = {}
        return engine

    def test_screen_time_alert_triggers_speak(self, world_model):
        engine = self._make_engine()
        world_model.user.screen_time.total_minutes = 130

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "画面" in a["args"]["message"]]
        assert len(speaks) == 1
        assert "目を休め" in speaks[0]["args"]["message"]

    def test_screen_time_below_threshold_no_action(self, world_model):
        engine = self._make_engine()
        world_model.user.screen_time.total_minutes = 60

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "画面" in a["args"]["message"]]
        assert len(speaks) == 0


class TestRuleEngineHRVRule:
    def _make_engine(self):
        from rule_engine import RuleEngine
        engine = RuleEngine()
        engine._cooldowns = {}
        return engine

    def test_low_hrv_triggers_speak(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.hrv.rmssd_ms = 15
        world_model.biometric_state.hrv.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "HRV" in a["args"]["message"]]
        assert len(speaks) == 1
        assert "15" in speaks[0]["args"]["message"]
        assert "自律神経" in speaks[0]["args"]["message"]

    def test_normal_hrv_no_action(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.hrv.rmssd_ms = 50
        world_model.biometric_state.hrv.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "HRV" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_hrv_none_no_action(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.hrv.rmssd_ms = None

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "HRV" in a["args"]["message"]]
        assert len(speaks) == 0


class TestRuleEngineBodyTempRule:
    def _make_engine(self):
        from rule_engine import RuleEngine
        engine = RuleEngine()
        engine._cooldowns = {}
        return engine

    def test_high_body_temp_triggers_speak(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.body_temperature.celsius = 38.2
        world_model.biometric_state.body_temperature.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "体温" in a["args"]["message"]]
        assert len(speaks) == 1
        assert "38.2" in speaks[0]["args"]["message"]

    def test_normal_body_temp_no_action(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.body_temperature.celsius = 36.5
        world_model.biometric_state.body_temperature.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "体温" in a["args"]["message"]]
        assert len(speaks) == 0


class TestRuleEngineRespiratoryRateRule:
    def _make_engine(self):
        from rule_engine import RuleEngine
        engine = RuleEngine()
        engine._cooldowns = {}
        return engine

    def test_high_resp_rate_triggers_speak(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.respiratory_rate.breaths_per_minute = 30
        world_model.biometric_state.respiratory_rate.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "呼吸" in a["args"]["message"]]
        assert len(speaks) == 1
        assert "深呼吸" in speaks[0]["args"]["message"]

    def test_normal_resp_rate_no_action(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.respiratory_rate.breaths_per_minute = 16
        world_model.biometric_state.respiratory_rate.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "呼吸" in a["args"]["message"]]
        assert len(speaks) == 0


# ===== Schedule Learner Persistence =====


class TestScheduleLearnerPersistence:
    def test_save_and_load_state(self, tmp_path):
        from schedule_learner import ScheduleLearner
        sl = ScheduleLearner()

        # Record some data
        import datetime as dt_mod
        ts1 = dt_mod.datetime(2026, 2, 16, 18, 30).timestamp()  # Monday
        ts2 = dt_mod.datetime(2026, 2, 17, 7, 0).timestamp()    # Tuesday

        sl.record_arrival(ts1)
        sl.record_wake(ts2)

        # Save
        state = sl.save_state()
        assert "arrival_history" in state
        assert "wake_history" in state

        # Load into new instance
        sl2 = ScheduleLearner()
        sl2.load_state(state)
        assert 0 in sl2._arrival_history  # Monday = 0
        assert 1 in sl2._wake_history     # Tuesday = 1

    def test_load_empty_state(self):
        from schedule_learner import ScheduleLearner
        sl = ScheduleLearner()
        sl.load_state({})
        assert sl._arrival_history == {}

    def test_load_none_state(self):
        from schedule_learner import ScheduleLearner
        sl = ScheduleLearner()
        sl.load_state(None)
        assert sl._arrival_history == {}

    def test_json_round_trip(self, tmp_path):
        """Test that state survives JSON serialization (string keys)."""
        from schedule_learner import ScheduleLearner
        sl = ScheduleLearner()

        import datetime as dt_mod
        ts = dt_mod.datetime(2026, 2, 18, 18, 0).timestamp()  # Wednesday
        sl.record_arrival(ts)

        state = sl.save_state()
        json_str = json.dumps(state)
        loaded = json.loads(json_str)

        sl2 = ScheduleLearner()
        sl2.load_state(loaded)
        # Keys are converted back from strings to ints
        assert 2 in sl2._arrival_history  # Wednesday = 2


# ===== Biometric Bridge Data Processor =====


class TestDataProcessorHRVFatigue:
    """Test HRV modifier in fatigue calculation."""

    def test_very_low_hrv_adds_fatigue(self):
        import sys
        from pathlib import Path
        bridge_src = str(Path(__file__).resolve().parent.parent / "services" / "biometric-bridge" / "src")
        sys.path.insert(0, bridge_src)
        try:
            from data_processor import DataProcessor, BiometricReading
            dp = DataProcessor()

            reading = BiometricReading(
                heart_rate=70,
                stress_level=30,
                hrv_ms=15,
                provider="test",
            )
            dp.process(reading)
            fatigue = dp.compute_fatigue()
            assert "very_low_hrv" in fatigue["factors"]
            assert fatigue["score"] > 0
        finally:
            sys.path.remove(bridge_src)

    def test_low_hrv_adds_moderate_fatigue(self):
        import sys
        from pathlib import Path
        bridge_src = str(Path(__file__).resolve().parent.parent / "services" / "biometric-bridge" / "src")
        sys.path.insert(0, bridge_src)
        try:
            from data_processor import DataProcessor, BiometricReading
            dp = DataProcessor()

            reading = BiometricReading(
                heart_rate=70,
                stress_level=30,
                hrv_ms=35,
                provider="test",
            )
            dp.process(reading)
            fatigue = dp.compute_fatigue()
            assert "low_hrv" in fatigue["factors"]
        finally:
            sys.path.remove(bridge_src)

    def test_normal_hrv_no_fatigue_modifier(self):
        import sys
        from pathlib import Path
        bridge_src = str(Path(__file__).resolve().parent.parent / "services" / "biometric-bridge" / "src")
        sys.path.insert(0, bridge_src)
        try:
            from data_processor import DataProcessor, BiometricReading
            dp = DataProcessor()

            reading = BiometricReading(
                heart_rate=70,
                stress_level=30,
                hrv_ms=60,
                provider="test",
            )
            dp.process(reading)
            fatigue = dp.compute_fatigue()
            assert "very_low_hrv" not in fatigue["factors"]
            assert "low_hrv" not in fatigue["factors"]
        finally:
            sys.path.remove(bridge_src)


# ===== Gadgetbridge Provider New Fields =====


class TestGadgetbridgeNewFields:
    """Test Gadgetbridge provider handles HRV, body temp, respiratory rate."""

    def _get_provider(self):
        import sys
        from pathlib import Path
        bridge_src = str(Path(__file__).resolve().parent.parent / "services" / "biometric-bridge" / "src")
        if bridge_src not in sys.path:
            sys.path.insert(0, bridge_src)
        from providers.gadgetbridge import GadgetbridgeProvider
        return GadgetbridgeProvider()

    def test_hrv_from_webhook(self):
        provider = self._get_provider()
        reading = provider.process_webhook({"hrv": 42})
        assert reading.hrv_ms == 42

    def test_hrv_alternative_key(self):
        provider = self._get_provider()
        reading = provider.process_webhook({"heart_rate_variability": 55})
        assert reading.hrv_ms == 55

    def test_body_temperature_from_webhook(self):
        provider = self._get_provider()
        reading = provider.process_webhook({"body_temperature": 36.5})
        assert reading.body_temperature == 36.5

    def test_body_temperature_range_check(self):
        """Temperature outside 30-45°C is discarded."""
        provider = self._get_provider()
        reading = provider.process_webhook({"body_temperature": 20.0})
        assert reading.body_temperature is None

    def test_respiratory_rate_from_webhook(self):
        provider = self._get_provider()
        reading = provider.process_webhook({"respiratory_rate": 16})
        assert reading.respiratory_rate == 16

    def test_respiratory_rate_alternative_key(self):
        provider = self._get_provider()
        reading = provider.process_webhook({"breathing_rate": 18})
        assert reading.respiratory_rate == 18

    def test_all_new_fields_together(self):
        provider = self._get_provider()
        reading = provider.process_webhook({
            "heart_rate": 72,
            "hrv": 45,
            "body_temperature": 36.8,
            "respiratory_rate": 16,
            "steps": 5000,
        })
        assert reading.heart_rate == 72
        assert reading.hrv_ms == 45
        assert reading.body_temperature == 36.8
        assert reading.respiratory_rate == 16
        assert reading.steps == 5000
