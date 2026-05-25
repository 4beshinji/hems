"""
Regression tests for RuleEngine facade threshold constants consumed by mixins.
"""

import importlib
import os

from world_model.data_classes import EnvironmentData, SpO2Data


def _reload_rule_engine(monkeypatch, **env):
    import rule_engine

    old_values = {key: os.environ.get(key) for key in env}
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    module = importlib.reload(rule_engine)

    def restore():
        for key, value in old_values.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        importlib.reload(rule_engine)

    return module, restore


def test_device_health_threshold_env_used_by_services_mixin(monkeypatch):
    rule_engine, restore = _reload_rule_engine(monkeypatch, HEMS_DEVICE_BATTERY_LOW=20)
    try:
        engine = rule_engine.RuleEngine()
        engine._device_cache = [{"device_id": "zigbee.remote", "battery_pct": 15}]

        actions = engine._evaluate_device_health_rules(now=2_000_000.0)

        assert len(actions) == 1
        assert actions[0]["args"]["title"] == "電池切れ間近: zigbee.remote"
    finally:
        restore()


def test_voc_sustain_threshold_env_used_by_facade_rule(monkeypatch, world_model):
    rule_engine, restore = _reload_rule_engine(
        monkeypatch,
        HEMS_THRESHOLD_VOC_HIGH=100,
        HEMS_VOC_SUSTAIN_SECONDS=1,
    )
    try:
        current_time = 2_000_000.0
        monkeypatch.setattr(rule_engine.time, "time", lambda: current_time)
        engine = rule_engine.RuleEngine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(voc=150)

        first = engine.evaluate(world_model)
        current_time = 2_000_002.0
        second = engine.evaluate(world_model)

        assert first == []
        assert any(action["tool"] == "speak" and "VOC" in action["args"]["message"] for action in second)
    finally:
        restore()


def test_critical_threshold_env_used_by_evaluate_critical(monkeypatch, world_model):
    rule_engine, restore = _reload_rule_engine(monkeypatch, HEMS_THRESHOLD_SPO2_CRITICAL_LOW=95)
    try:
        monkeypatch.setattr(rule_engine.time, "time", lambda: 2_000_000.0)
        engine = rule_engine.RuleEngine()
        world_model.biometric_state.spo2 = SpO2Data(percent=94, last_update=1_999_950.0)

        actions = engine.evaluate_critical(world_model)

        assert len(actions) == 1
        assert actions[0]["tool"] == "speak"
        assert "血中酸素濃度" in actions[0]["args"]["message"]
    finally:
        restore()
