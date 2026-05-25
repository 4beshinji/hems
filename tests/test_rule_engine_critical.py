"""
Regression tests for RuleEngine.evaluate_critical.
"""

from rule_engine import RuleEngine
from world_model.data_classes import BinarySensorState, EnvironmentData, HeartRateData, SleepData, SpO2Data


def test_critical_co2_creates_task_and_speaks(monkeypatch, world_model):
    import rule_engine

    monkeypatch.setattr(rule_engine.time, "time", lambda: 2_000_000.0)
    engine = RuleEngine()
    world_model._get_zone("office").environment = EnvironmentData(co2=1600)

    actions = engine.evaluate_critical(world_model)

    assert any(action["tool"] == "create_task" and "CO2危険レベル" in action["args"]["title"] for action in actions)
    assert any(action["tool"] == "speak" and "CO2濃度" in action["args"]["message"] for action in actions)


def test_critical_temperature_high_and_low(monkeypatch, world_model):
    import rule_engine

    monkeypatch.setattr(rule_engine.time, "time", lambda: 2_000_000.0)
    engine = RuleEngine()
    world_model._get_zone("hot_room").environment = EnvironmentData(temperature=41.0)
    world_model._get_zone("cold_room").environment = EnvironmentData(temperature=4.0)

    actions = engine.evaluate_critical(world_model)
    messages = [action["args"]["message"] for action in actions if action["tool"] == "speak"]

    assert any("hot_roomの室温が41.0" in message for message in messages)
    assert any("cold_roomの室温が4.0" in message for message in messages)


def test_critical_moisture_creates_task_and_speaks(monkeypatch, world_model):
    import rule_engine

    monkeypatch.setattr(rule_engine.time, "time", lambda: 2_000_000.0)
    engine = RuleEngine()
    world_model.home_devices.binary_sensors["binary_sensor.leak"] = BinarySensorState(
        entity_id="binary_sensor.leak",
        device_class="moisture",
        state=True,
    )

    actions = engine.evaluate_critical(world_model)

    assert any(action["tool"] == "create_task" and "水漏れ検知" in action["args"]["title"] for action in actions)
    assert any(action["tool"] == "speak" and "水漏れ" in action["args"]["message"] for action in actions)


def test_critical_spo2_recent_only(monkeypatch, world_model):
    import rule_engine

    monkeypatch.setattr(rule_engine.time, "time", lambda: 2_000_000.0)
    engine = RuleEngine()
    world_model.biometric_state.spo2 = SpO2Data(percent=86, last_update=1_999_000.0)

    stale_actions = engine.evaluate_critical(world_model)
    world_model.biometric_state.spo2 = SpO2Data(percent=86, last_update=1_999_950.0)
    recent_actions = engine.evaluate_critical(world_model)

    assert stale_actions == []
    assert any("血中酸素濃度" in action["args"]["message"] for action in recent_actions)


def test_critical_sleep_hr_recent_only(monkeypatch, world_model):
    import rule_engine

    monkeypatch.setattr(rule_engine.time, "time", lambda: 2_000_000.0)
    engine = RuleEngine()
    world_model.biometric_state.sleep = SleepData(stage="deep")
    world_model.biometric_state.heart_rate = HeartRateData(bpm=160, last_update=1_999_000.0)

    stale_actions = engine.evaluate_critical(world_model)
    world_model.biometric_state.heart_rate = HeartRateData(bpm=160, last_update=1_999_950.0)
    recent_actions = engine.evaluate_critical(world_model)

    assert stale_actions == []
    assert any("睡眠中に心拍数" in action["args"]["message"] for action in recent_actions)
