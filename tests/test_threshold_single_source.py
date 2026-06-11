"""
W2.1 behavior-invariance tests for threshold single-sourcing.

Guards that the world_model module threshold constants and the RuleThresholds
dataclass are derived from a single source of truth and stay value-identical.
"""

import dataclasses
import os

import pytest

from rules.config import RuleThresholds, load_rule_thresholds

# Golden default values (env unset). RuleThresholds fields + world_model
# threshold constants. Values copied verbatim from the design note §2-A/§2-B.
GOLDEN_RULE_THRESHOLDS = {
    # world-model-derived (site A)
    "co2_high": 1000,
    "co2_critical": 1500,
    "temp_high": 28,
    "temp_low": 16,
    "sedentary_minutes": 60,
    "pc_cpu_high": 90,
    "pc_memory_high": 90,
    "pc_gpu_temp_high": 85,
    "pc_disk_high": 90,
    "hr_high": 120,
    "hr_low": 45,
    "spo2_low": 92,
    "stress_high": 80,
    "humidity_high": 70,
    "humidity_low": 30,
    "hrv_low": 20,
    "body_temp_high": 37.5,
    "respiratory_rate_high": 25,
    "screen_time_alert_minutes": 120,
    "power_idle_watts": 5.0,
    "pm25_high": 35.0,
    # critical
    "temp_critical_high": 40.0,
    "temp_critical_low": 5.0,
    "spo2_critical_low": 88,
    "hr_critical_sleep": 150,
    # biometric stale
    "biometric_stale_minutes": 30,
    # heavy process
    "pc_proc_cpu_high": 90.0,
    "pc_proc_cpu_sustain_s": 300,
    "pc_proc_mem_high_gb": 4.0,
    "pc_proc_cooldown_s": 1800,
    # device health
    "device_battery_low": 10,
    "device_lqi_low": 50,
    "device_stale_hours": 24,
    # gpu
    "gpu_type": "none",
    "gpu_high_load_threshold": 80,
    # sensor utilization
    "soil_moisture_low": 25.0,
    "auto_water_enabled": False,
    "auto_water_duration_s": 45,
    "voc_high_threshold": 500.0,
    "voc_sustain_seconds": 120,
    "voc_cooldown_seconds": 1800,
    "pm25_native_high": 35.0,
    "low_pressure_threshold": 1000.0,
    "low_pressure_sustain_s": 3 * 3600,
    "illuminance_low_lx": 20.0,
    "illuminance_low_sustain_s": 600,
    "illuminance_high_lx": 50000.0,
    "illuminance_high_sustain_s": 600,
    # lighting automation
    "absence_lighting_enabled": True,
    "absence_lighting_interval": 1800,
    "absence_lighting_start_hour": 17,
    "absence_lighting_end_hour": 23,
    "circadian_enabled": True,
    "circadian_interval": 1800,
}


def _clean_env(monkeypatch):
    """Remove all threshold env vars so defaults are exercised."""
    prefixes = (
        "HEMS_THRESHOLD_",
        "HEMS_PROC_",
        "HEMS_VOC_",
        "HEMS_DEVICE_",
        "HEMS_CIRCADIAN_",
        "HEMS_ABSENCE_",
        "HEMS_LIGHT_",
        "HEMS_PRESSURE_",
        "HEMS_AUTO_WATER",
        "HEMS_ENABLE_AUTO_WATER",
        "HEMS_BIOMETRIC_STALE",
        "HEMS_ENV_STALE",
        "HEMS_ZONE_BLIND",
        "GPU_TYPE",
        "GPU_HIGH_LOAD_THRESHOLD",
    )
    for key in list(os.environ):
        if key.startswith(prefixes):
            monkeypatch.delenv(key, raising=False)


def test_rule_thresholds_golden_snapshot(monkeypatch):
    _clean_env(monkeypatch)
    rt = load_rule_thresholds()
    for field_name, expected in GOLDEN_RULE_THRESHOLDS.items():
        assert getattr(rt, field_name) == expected, field_name


def test_world_model_thresholds_golden_snapshot(monkeypatch):
    _clean_env(monkeypatch)
    from world_model.world_model import WorldModel

    rt = WorldModel().thresholds
    for field_name, expected in GOLDEN_RULE_THRESHOLDS.items():
        assert getattr(rt, field_name) == expected, field_name


def test_ab_identity_world_model_vs_rule_engine(monkeypatch):
    """After constructor DI (W2.3) both engines must derive from one source.

    The strongest guarantee — and what Brain actually wires (main.py shares the
    WorldModel's instance) — is that WorldModel().thresholds and a RuleEngine
    built from it are the *same* RuleThresholds instance, and value-identical to
    a freshly loaded one.
    """
    _clean_env(monkeypatch)
    from rule_engine import RuleEngine
    from world_model.world_model import WorldModel

    wm = WorldModel()
    engine = RuleEngine(thresholds=wm.thresholds)
    assert engine.thresholds is wm.thresholds  # shared single instance
    rt = load_rule_thresholds()
    for field_name in GOLDEN_RULE_THRESHOLDS:
        assert getattr(wm.thresholds, field_name) == getattr(rt, field_name), field_name


def test_env_override_reflected_in_both(monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("HEMS_THRESHOLD_CO2_HIGH", "2000")
    monkeypatch.setenv("HEMS_THRESHOLD_TEMP_HIGH", "33")
    from rule_engine import RuleEngine
    from world_model.world_model import WorldModel

    wm = WorldModel()
    engine = RuleEngine(thresholds=wm.thresholds)
    rt = load_rule_thresholds()
    assert wm.thresholds.co2_high == 2000
    assert engine.thresholds.co2_high == 2000
    assert rt.co2_high == 2000
    assert wm.thresholds.temp_high == 33
    assert engine.thresholds.temp_high == 33
    assert rt.temp_high == 33


def test_pm25_native_backward_compat_warning(monkeypatch, caplog):
    _clean_env(monkeypatch)
    monkeypatch.setenv("HEMS_THRESHOLD_PM25_NATIVE", "55")
    # loguru does not propagate to caplog by default; capture via a sink.
    from loguru import logger

    records = []
    sink_id = logger.add(lambda m: records.append(m.record["message"]), level="WARNING")
    try:
        rt = load_rule_thresholds()
    finally:
        logger.remove(sink_id)

    assert rt.pm25_native_high == 55.0
    assert any("HEMS_THRESHOLD_PM25_NATIVE" in msg and "deprecated" in msg for msg in records)


def test_pm25_native_falls_back_to_canonical(monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("HEMS_THRESHOLD_PM25_HIGH", "42")
    rt = load_rule_thresholds()
    assert rt.pm25_high == 42.0
    assert rt.pm25_native_high == 42.0


def test_rule_thresholds_is_frozen():
    rt = load_rule_thresholds()
    assert isinstance(rt, RuleThresholds)
    with pytest.raises(dataclasses.FrozenInstanceError):
        rt.co2_high = 999  # type: ignore[misc]
