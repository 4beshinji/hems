"""
Regression tests for RuleEngine facade wiring after domain mixin extraction.
"""

from unittest.mock import AsyncMock

import pytest

from rule_engine import RuleEngine
from world_model.data_classes import HeartRateData, WeatherForecast


def test_rule_engine_exposes_all_domain_mixin_methods():
    engine = RuleEngine()
    method_names = [
        "_evaluate_biometric_rules",
        "_evaluate_gas_rules",
        "_evaluate_home_rules",
        "_evaluate_zigbee_sensor_rules",
        "_evaluate_weather_rules",
        "_evaluate_service_vip_rules",
        "_evaluate_device_health_rules",
        "_evaluate_perception_rules",
        "_evaluate_shopping_rules",
    ]
    missing = [name for name in method_names if not callable(getattr(engine, name, None))]
    assert missing == []


def test_mixin_rules_share_facade_cooldown_store(world_model):
    engine = RuleEngine()
    now = 2_000_000.0
    world_model.weather.last_update = now
    world_model.weather.forecast = [WeatherForecast(temperature=34)]
    world_model.biometric_state.heart_rate = HeartRateData(bpm=130, last_update=now)

    weather_actions = engine._evaluate_weather_rules(world_model, now)
    biometric_actions = engine._evaluate_biometric_rules(world_model, now)

    assert any("猛暑" in action["args"]["message"] for action in weather_actions)
    assert any("心拍数" in action["args"]["message"] for action in biometric_actions)
    assert engine._cooldowns["weather_hot_forecast"] == now
    assert engine._cooldowns["bio_hr_high"] == now


@pytest.mark.asyncio
async def test_refresh_devices_populates_cache_and_respects_ttl(monkeypatch):
    import rule_engine

    engine = RuleEngine()
    engine.device_dispatcher = AsyncMock()
    engine.device_dispatcher.list_all = AsyncMock(
        side_effect=[
            [{"device_id": "light.office"}],
            [{"device_id": "light.kitchen"}],
        ]
    )

    monkeypatch.setattr(rule_engine.time, "time", lambda: 1000.0)
    await engine.refresh_devices()
    assert engine._device_cache == [{"device_id": "light.office"}]
    assert engine._device_cache_ts == 1000.0
    assert engine.device_dispatcher.list_all.await_count == 1

    monkeypatch.setattr(rule_engine.time, "time", lambda: 1030.0)
    await engine.refresh_devices()
    assert engine._device_cache == [{"device_id": "light.office"}]
    assert engine.device_dispatcher.list_all.await_count == 1

    monkeypatch.setattr(rule_engine.time, "time", lambda: 1061.0)
    await engine.refresh_devices()
    assert engine._device_cache == [{"device_id": "light.kitchen"}]
    assert engine._device_cache_ts == 1061.0
    assert engine.device_dispatcher.list_all.await_count == 2


@pytest.mark.asyncio
async def test_refresh_devices_no_dispatcher_is_noop():
    engine = RuleEngine()
    await engine.refresh_devices()
    assert engine._device_cache == []
