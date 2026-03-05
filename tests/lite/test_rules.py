"""
Tests for HEMS Lite Sentinel rule engine.
Run: python -m pytest tests/lite/test_rules.py -v
"""
import sys
import os
import time

# Add sentinel src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/sentinel/src"))

from state import OccupantState
from rules import RuleEngine, AlertLevel


def _make_state(**kwargs) -> OccupantState:
    s = OccupantState()
    now = time.time()
    for k, v in kwargs.items():
        if k == "hr":
            s.update_biometric("heart_rate", v)
        elif k == "spo2":
            s.update_biometric("spo2", v)
        elif k == "stress":
            s.update_biometric("stress", v)
        elif k == "fatigue":
            s.update_biometric("fatigue", v)
        elif k == "hrv":
            s.update_biometric("hrv", v)
        elif k == "body_temp":
            s.update_biometric("body_temp", v)
        elif k == "respiratory_rate":
            s.update_biometric("respiratory_rate", v)
        elif k == "temperature":
            s.update_environment("living_room", temperature=v)
        elif k == "co2":
            s.update_environment("living_room", co2=v)
        elif k == "humidity":
            s.update_environment("living_room", humidity=v)
    return s


class TestCriticalRules:
    def test_spo2_critical(self):
        engine = RuleEngine()
        state = _make_state(spo2=85)
        alerts = engine.evaluate(state)
        critical = [a for a in alerts if a.level == AlertLevel.CRITICAL and a.rule_id == "C1"]
        assert len(critical) == 1
        assert "85" in critical[0].body

    def test_hr_critical_low(self):
        engine = RuleEngine()
        state = _make_state(hr=35)
        alerts = engine.evaluate(state)
        critical = [a for a in alerts if a.level == AlertLevel.CRITICAL and a.rule_id == "C2"]
        assert len(critical) == 1

    def test_hr_critical_high(self):
        engine = RuleEngine()
        state = _make_state(hr=160)
        alerts = engine.evaluate(state)
        critical = [a for a in alerts if a.level == AlertLevel.CRITICAL and a.rule_id == "C3"]
        assert len(critical) == 1

    def test_normal_hr_no_critical(self):
        engine = RuleEngine()
        state = _make_state(hr=75)
        alerts = engine.evaluate(state)
        critical = [a for a in alerts if a.level == AlertLevel.CRITICAL]
        assert len(critical) == 0

    def test_normal_spo2_no_alert(self):
        engine = RuleEngine()
        state = _make_state(spo2=98)
        alerts = engine.evaluate(state)
        spo2_alerts = [a for a in alerts if "spo2" in a.rule_id.lower() or "SpO2" in a.title]
        assert len(spo2_alerts) == 0


class TestHighRules:
    def test_hr_high(self):
        engine = RuleEngine()
        state = _make_state(hr=130)
        alerts = engine.evaluate(state)
        high = [a for a in alerts if a.level == AlertLevel.HIGH and a.rule_id == "H2"]
        assert len(high) == 1

    def test_spo2_low_but_not_critical(self):
        engine = RuleEngine()
        state = _make_state(spo2=90)
        alerts = engine.evaluate(state)
        high = [a for a in alerts if a.level == AlertLevel.HIGH and a.rule_id == "H1"]
        assert len(high) == 1

    def test_temp_extreme_high(self):
        engine = RuleEngine()
        state = _make_state(temperature=35)
        alerts = engine.evaluate(state)
        high = [a for a in alerts if a.level == AlertLevel.HIGH and "H4" in a.rule_id]
        assert len(high) == 1

    def test_temp_extreme_low(self):
        engine = RuleEngine()
        state = _make_state(temperature=5)
        alerts = engine.evaluate(state)
        high = [a for a in alerts if a.level == AlertLevel.HIGH and "H4" in a.rule_id]
        assert len(high) == 1

    def test_body_temp_high(self):
        engine = RuleEngine()
        state = _make_state(body_temp=38.2)
        alerts = engine.evaluate(state)
        high = [a for a in alerts if a.rule_id == "H7"]
        assert len(high) == 1

    def test_respiratory_high(self):
        engine = RuleEngine()
        state = _make_state(respiratory_rate=30)
        alerts = engine.evaluate(state)
        high = [a for a in alerts if a.rule_id == "H8"]
        assert len(high) == 1


class TestNormalRules:
    def test_stress_high(self):
        engine = RuleEngine()
        state = _make_state(stress=85)
        alerts = engine.evaluate(state)
        normal = [a for a in alerts if a.level == AlertLevel.NORMAL and a.rule_id == "N2"]
        assert len(normal) == 1

    def test_co2_high(self):
        engine = RuleEngine()
        state = _make_state(co2=1200)
        alerts = engine.evaluate(state)
        co2 = [a for a in alerts if "co2" in a.rule_id]
        assert len(co2) == 1

    def test_co2_critical(self):
        engine = RuleEngine()
        state = _make_state(co2=1600)
        alerts = engine.evaluate(state)
        co2_high = [a for a in alerts if a.level == AlertLevel.HIGH and "co2" in a.rule_id]
        assert len(co2_high) == 1

    def test_humidity_high(self):
        engine = RuleEngine()
        state = _make_state(humidity=80)
        alerts = engine.evaluate(state)
        hum = [a for a in alerts if "humidity" in a.rule_id or "hum" in a.rule_id]
        assert len(hum) == 1

    def test_humidity_low(self):
        engine = RuleEngine()
        state = _make_state(humidity=20)
        alerts = engine.evaluate(state)
        hum = [a for a in alerts if "humidity" in a.rule_id or "hum" in a.rule_id]
        assert len(hum) == 1


class TestCooldowns:
    def test_cooldown_prevents_duplicate(self):
        engine = RuleEngine()
        state = _make_state(hr=160)
        alerts1 = engine.evaluate(state)
        alerts2 = engine.evaluate(state)
        critical1 = [a for a in alerts1 if a.level == AlertLevel.CRITICAL]
        critical2 = [a for a in alerts2 if a.level == AlertLevel.CRITICAL]
        # First evaluation fires, second is cooled down
        # (CRITICAL has 0 cooldown, so it should fire both times)
        assert len(critical1) >= 1
        assert len(critical2) >= 1  # CRITICAL has no cooldown

    def test_high_cooldown(self):
        engine = RuleEngine()
        state = _make_state(hr=130)
        alerts1 = engine.evaluate(state)
        alerts2 = engine.evaluate(state)
        high1 = [a for a in alerts1 if a.level == AlertLevel.HIGH and a.rule_id == "H2"]
        high2 = [a for a in alerts2 if a.level == AlertLevel.HIGH and a.rule_id == "H2"]
        assert len(high1) == 1
        assert len(high2) == 0  # Cooled down (5min)


class TestMultipleAlerts:
    def test_multiple_critical(self):
        engine = RuleEngine()
        state = _make_state(hr=160, spo2=85)
        alerts = engine.evaluate(state)
        critical = [a for a in alerts if a.level == AlertLevel.CRITICAL]
        assert len(critical) >= 2  # Both HR and SpO2

    def test_mixed_levels(self):
        engine = RuleEngine()
        state = _make_state(hr=130, stress=85, co2=1200)
        alerts = engine.evaluate(state)
        assert any(a.level == AlertLevel.HIGH for a in alerts)
        assert any(a.level == AlertLevel.NORMAL for a in alerts)
