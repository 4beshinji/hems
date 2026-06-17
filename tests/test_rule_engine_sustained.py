"""
Regression tests for RuleEngine sustained-condition trackers.
"""

from datetime import datetime
from unittest.mock import patch

from rule_engine import RuleEngine
from rules.config import load_rule_thresholds
from world_model.data_classes import EnvironmentData, ProcessInfo

_THRESH = load_rule_thresholds()
ILLUMINANCE_LOW_SUSTAIN_S = _THRESH.illuminance_low_sustain_s
LOW_PRESSURE_SUSTAIN_S = _THRESH.low_pressure_sustain_s
PC_PROC_CPU_SUSTAIN_S = _THRESH.pc_proc_cpu_sustain_s


def test_voc_high_requires_sustain_and_resets_when_normal(monkeypatch, world_model):
    import rule_engine

    current_time = 2_000_000.0
    monkeypatch.setattr(rule_engine.time, "time", lambda: current_time)
    engine = RuleEngine()
    zone = world_model._get_zone("office")
    zone.environment = EnvironmentData(voc=600)

    assert engine.evaluate(world_model) == []
    assert engine._voc_high_since["office"] == 2_000_000.0

    zone.environment.voc = 100
    engine.evaluate(world_model)

    assert "office" not in engine._voc_high_since


def test_low_pressure_sustained_daily_cooldown(monkeypatch, world_model):
    import rule_engine

    current_time = 2_000_000.0
    monkeypatch.setattr(rule_engine.time, "time", lambda: current_time)
    engine = RuleEngine()
    zone = world_model._get_zone("office")
    zone.environment = EnvironmentData(pressure=990)

    first = engine.evaluate(world_model)
    current_time = 2_000_000.0 + LOW_PRESSURE_SUSTAIN_S + 1
    second = engine.evaluate(world_model)
    third = engine.evaluate(world_model)

    assert not any("気圧" in action["args"].get("message", "") for action in first if action["tool"] == "speak")
    assert any("長時間低め" in action["args"].get("message", "") for action in second if action["tool"] == "speak")
    assert not any("長時間低め" in action["args"].get("message", "") for action in third if action["tool"] == "speak")


def test_low_light_sustained_creates_maintenance_task(monkeypatch, world_model):
    import rule_engine

    current_time = 2_000_000.0
    monkeypatch.setattr(rule_engine.time, "time", lambda: current_time)
    engine = RuleEngine()
    zone = world_model._get_zone("office")
    zone.environment = EnvironmentData(light=10)

    with patch("rules.environment.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 24, 12, 0)
        first = engine.evaluate(world_model)
        current_time = 2_000_000.0 + ILLUMINANCE_LOW_SUSTAIN_S + 1
        second = engine.evaluate(world_model)

    assert not any(action["args"].get("title") == "officeの照度センサー確認" for action in first)
    assert any(action["args"].get("title") == "officeの照度センサー確認" for action in second)


def test_high_light_sustained_closes_cover(monkeypatch, world_model):
    import rule_engine

    current_time = 2_000_000.0
    monkeypatch.setattr(rule_engine.time, "time", lambda: current_time)
    engine = RuleEngine()
    engine._device_cache = [
        {
            "device_id": "cover.office",
            "device_class": "cover",
            "is_enabled": True,
            "zone": "office",
        }
    ]
    zone = world_model._get_zone("office")
    zone.environment = EnvironmentData(light=60_000)

    with patch("rules.environment.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 24, 12, 0)
        first = engine.evaluate(world_model)
        current_time = 2_000_601.0
        second = engine.evaluate(world_model)

    assert not any(action.get("args", {}).get("device_id") == "cover.office" for action in first)
    assert any(
        action["tool"] == "control_actuator"
        and action["args"]["device_id"] == "cover.office"
        and action["args"]["action"] == "set_position"
        for action in second
    )


def test_heavy_process_cpu_sustained_triggers_and_gc_removes_stale_process(monkeypatch, world_model):
    import rule_engine

    current_time = 2_000_000.0
    monkeypatch.setattr(rule_engine.time, "time", lambda: current_time)
    engine = RuleEngine()
    world_model.pc_state.top_processes = [ProcessInfo(name="compiler", cpu_percent=95, mem_mb=256)]

    first = engine.evaluate(world_model)
    current_time = 2_000_000.0 + PC_PROC_CPU_SUSTAIN_S + 1
    second = engine.evaluate(world_model)
    world_model.pc_state.top_processes = []
    third = engine.evaluate(world_model)

    assert not any("compiler" in action["args"].get("message", "") for action in first if action["tool"] == "speak")
    assert any("compiler" in action["args"].get("message", "") for action in second if action["tool"] == "speak")
    assert third == []
    assert "compiler" not in engine._heavy_proc_since
