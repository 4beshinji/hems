"""
Regression tests for RuleEngine threshold env overrides consumed by mixins.

After W2.3 the RuleEngine takes thresholds via constructor DI
(`RuleEngine(thresholds=load_rule_thresholds())`), so env overrides are
exercised by building the engine after setting the env var — no module reload.
The property under test is unchanged: env overrides must reach the rule logic.
"""

import rule_engine as rule_engine_mod
from rule_engine import RuleEngine
from rules.config import load_rule_thresholds
from world_model.data_classes import EnvironmentData, SpO2Data


def test_device_health_threshold_env_used_by_services_mixin(monkeypatch):
    monkeypatch.setenv("HEMS_DEVICE_BATTERY_LOW", "20")
    engine = RuleEngine(thresholds=load_rule_thresholds())
    assert engine.thresholds.device_battery_low == 20
    engine._device_cache = [{"device_id": "zigbee.remote", "battery_pct": 15}]

    actions = engine._evaluate_device_health_rules(now=2_000_000.0)

    assert len(actions) == 1
    assert actions[0]["args"]["title"] == "電池切れ間近: zigbee.remote"


def test_voc_sustain_threshold_env_used_by_facade_rule(monkeypatch, world_model):
    monkeypatch.setenv("HEMS_THRESHOLD_VOC_HIGH", "100")
    monkeypatch.setenv("HEMS_VOC_SUSTAIN_SECONDS", "1")

    current_time = 2_000_000.0
    monkeypatch.setattr(rule_engine_mod.time, "time", lambda: current_time)
    engine = RuleEngine(thresholds=load_rule_thresholds())
    assert engine.thresholds.voc_high_threshold == 100
    assert engine.thresholds.voc_sustain_seconds == 1
    zone = world_model._get_zone("office")
    zone.environment = EnvironmentData(voc=150)

    first = engine.evaluate(world_model)
    current_time = 2_000_002.0
    second = engine.evaluate(world_model)

    assert first == []
    assert any(action["tool"] == "speak" and "VOC" in action["args"]["message"] for action in second)


def test_critical_threshold_env_used_by_evaluate_critical(monkeypatch, world_model):
    monkeypatch.setenv("HEMS_THRESHOLD_SPO2_CRITICAL_LOW", "95")
    monkeypatch.setattr(rule_engine_mod.time, "time", lambda: 2_000_000.0)
    engine = RuleEngine(thresholds=load_rule_thresholds())
    assert engine.thresholds.spo2_critical_low == 95
    world_model.biometric_state.spo2 = SpO2Data(percent=94, last_update=1_999_950.0)

    actions = engine.evaluate_critical(world_model)

    assert len(actions) == 1
    assert actions[0]["tool"] == "speak"
    assert "血中酸素濃度" in actions[0]["args"]["message"]
