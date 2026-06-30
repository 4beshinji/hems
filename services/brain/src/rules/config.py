"""Configuration for RuleEngine facade and domain mixins."""

import os
from dataclasses import dataclass, field

from loguru import logger


def _env_bool(name: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).lower() == "true"


def _pm25_native_default() -> float:
    """Resolve pm25_native_high default with backward-compat for the deprecated env var.

    Canonical env var is HEMS_THRESHOLD_PM25_HIGH (shared with the world_model
    PM2.5 estimate threshold). The legacy HEMS_THRESHOLD_PM25_NATIVE is honored
    for backward compatibility: if set, it takes precedence and emits a
    deprecation warning. Otherwise the canonical var (default 35) is used.
    """
    legacy = os.getenv("HEMS_THRESHOLD_PM25_NATIVE")
    if legacy is not None:
        logger.warning(
            "HEMS_THRESHOLD_PM25_NATIVE is deprecated; use HEMS_THRESHOLD_PM25_HIGH. "
            "Honoring the legacy value for backward compatibility."
        )
        return float(legacy)
    return float(os.getenv("HEMS_THRESHOLD_PM25_HIGH", "35"))


@dataclass(frozen=True)
class RuleThresholds:
    # Critical thresholds used only in low-power mode.
    temp_critical_high: float
    temp_critical_low: float
    spo2_critical_low: int
    hr_critical_sleep: int

    # Biometric stale data detection.
    biometric_stale_minutes: int

    # Heavy process thresholds.
    pc_proc_cpu_high: float
    pc_proc_cpu_sustain_s: int
    pc_proc_mem_high_gb: float
    pc_proc_cooldown_s: int
    pc_proc_heavy_exclude: list[str] = field(default_factory=list)

    # Device health thresholds.
    device_battery_low: int = 10
    device_lqi_low: int = 50
    device_stale_hours: int = 24

    # GPU fallback.
    gpu_type: str = "none"
    gpu_high_load_threshold: int = 80

    # Sensor utilization thresholds.
    soil_moisture_low: float = 25.0
    auto_water_enabled: bool = False
    auto_water_duration_s: int = 45
    voc_high_threshold: float = 500.0
    voc_sustain_seconds: int = 120
    voc_cooldown_seconds: int = 1800
    pm25_native_high: float = 35.0
    low_pressure_threshold: float = 1000.0
    low_pressure_sustain_s: int = 3 * 3600
    illuminance_low_lx: float = 20.0
    illuminance_low_sustain_s: int = 600
    illuminance_high_lx: float = 50000.0
    illuminance_high_sustain_s: int = 600

    # Lighting automation config.
    absence_lighting_enabled: bool = True
    absence_lighting_interval: int = 1800
    absence_lighting_start_hour: int = 17
    absence_lighting_end_hour: int = 23
    circadian_enabled: bool = True
    circadian_interval: int = 1800
    circadian_curve: list[tuple[int, int, int]] = field(default_factory=list)

    # World-model-derived event/alert thresholds (single source of truth).
    # env var names, defaults and types copied verbatim from the former
    # world_model.world_model module constants. The freshness time-windows
    # (ENV_STALE_SEC / ZONE_BLIND_SEC) are intentionally NOT included here.
    co2_high: int = 1000
    co2_critical: int = 1500
    temp_high: int = 28
    temp_low: int = 16
    sedentary_minutes: int = 60
    pc_cpu_high: int = 90
    pc_memory_high: int = 90
    pc_gpu_temp_high: int = 85
    pc_disk_high: int = 90
    hr_high: int = 120
    hr_low: int = 45
    spo2_low: int = 92
    stress_high: int = 80
    humidity_high: int = 70
    humidity_low: int = 30
    hrv_low: int = 20
    body_temp_high: float = 37.5
    respiratory_rate_high: int = 25
    screen_time_alert_minutes: int = 120
    power_idle_watts: float = 5.0
    pm25_high: float = 35.0


class AdaptiveRuleThresholds:
    """Dynamic wrapper around RuleThresholds that applies learned offsets.

    Allows the rule engine to keep using `self.thresholds.co2_high` while the
    effective value drifts based on feedback and distribution shift. The base
    RuleThresholds instance is never mutated; offsets are stored separately.
    """

    def __init__(self, base: RuleThresholds, offsets: dict[str, float] | None = None):
        self._base = base
        self._offsets: dict[str, float] = dict(offsets or {})

    def __getattr__(self, name: str):
        value = getattr(self._base, name)
        if name in self._offsets and isinstance(value, (int, float)):
            return value + self._offsets[name]
        return value

    def __setattr__(self, name: str, value) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            setattr(self._base, name, value)

    def set_offset(self, metric_key: str, offset: float) -> None:
        self._offsets[metric_key] = offset

    def get_offset(self, metric_key: str) -> float:
        return self._offsets.get(metric_key, 0.0)

    def get_effective(self, metric_key: str) -> float | None:
        base = getattr(self._base, metric_key, None)
        if base is None:
            return None
        return base + self._offsets.get(metric_key, 0.0)

    @property
    def base(self) -> RuleThresholds:
        return self._base

    @property
    def offsets(self) -> dict[str, float]:
        return dict(self._offsets)


def load_rule_thresholds() -> RuleThresholds:
    return RuleThresholds(
        temp_critical_high=float(os.getenv("HEMS_THRESHOLD_TEMP_CRITICAL_HIGH", "40.0")),
        temp_critical_low=float(os.getenv("HEMS_THRESHOLD_TEMP_CRITICAL_LOW", "5.0")),
        spo2_critical_low=int(os.getenv("HEMS_THRESHOLD_SPO2_CRITICAL_LOW", "88")),
        hr_critical_sleep=int(os.getenv("HEMS_THRESHOLD_HR_CRITICAL_SLEEP", "150")),
        biometric_stale_minutes=int(os.getenv("HEMS_BIOMETRIC_STALE_MINUTES", "30")),
        co2_high=int(os.getenv("HEMS_THRESHOLD_CO2_HIGH", "1000")),
        co2_critical=int(os.getenv("HEMS_THRESHOLD_CO2_CRITICAL", "1500")),
        temp_high=int(os.getenv("HEMS_THRESHOLD_TEMP_HIGH", "28")),
        temp_low=int(os.getenv("HEMS_THRESHOLD_TEMP_LOW", "16")),
        sedentary_minutes=int(os.getenv("HEMS_THRESHOLD_SEDENTARY_MINUTES", "60")),
        pc_cpu_high=int(os.getenv("HEMS_THRESHOLD_PC_CPU_HIGH", "90")),
        pc_memory_high=int(os.getenv("HEMS_THRESHOLD_PC_MEMORY_HIGH", "90")),
        pc_gpu_temp_high=int(os.getenv("HEMS_THRESHOLD_PC_GPU_TEMP_HIGH", "85")),
        pc_disk_high=int(os.getenv("HEMS_THRESHOLD_PC_DISK_HIGH", "90")),
        hr_high=int(os.getenv("HEMS_THRESHOLD_HR_HIGH", "120")),
        hr_low=int(os.getenv("HEMS_THRESHOLD_HR_LOW", "45")),
        spo2_low=int(os.getenv("HEMS_THRESHOLD_SPO2_LOW", "92")),
        stress_high=int(os.getenv("HEMS_THRESHOLD_STRESS_HIGH", "80")),
        humidity_high=int(os.getenv("HEMS_THRESHOLD_HUMIDITY_HIGH", "70")),
        humidity_low=int(os.getenv("HEMS_THRESHOLD_HUMIDITY_LOW", "30")),
        hrv_low=int(os.getenv("HEMS_THRESHOLD_HRV_LOW", "20")),
        body_temp_high=float(os.getenv("HEMS_THRESHOLD_BODY_TEMP_HIGH", "37.5")),
        respiratory_rate_high=int(os.getenv("HEMS_THRESHOLD_RESPIRATORY_RATE_HIGH", "25")),
        screen_time_alert_minutes=int(os.getenv("HEMS_THRESHOLD_SCREEN_TIME_MINUTES", "120")),
        power_idle_watts=float(os.getenv("HEMS_THRESHOLD_POWER_IDLE_WATTS", "5")),
        pm25_high=float(os.getenv("HEMS_THRESHOLD_PM25_HIGH", "35")),
        pc_proc_cpu_high=float(os.getenv("HEMS_PROC_CPU_HIGH", "90")),
        pc_proc_cpu_sustain_s=int(os.getenv("HEMS_PROC_CPU_SUSTAIN_S", "300")),
        pc_proc_mem_high_gb=float(os.getenv("HEMS_PROC_MEM_HIGH_GB", "4.0")),
        pc_proc_cooldown_s=int(os.getenv("HEMS_PROC_COOLDOWN_S", "1800")),
        pc_proc_heavy_exclude=[
            s.strip().lower() for s in os.getenv("HEMS_PROC_HEAVY_EXCLUDE", "").split(",") if s.strip()
        ],
        device_battery_low=int(os.getenv("HEMS_DEVICE_BATTERY_LOW", "10")),
        device_lqi_low=int(os.getenv("HEMS_DEVICE_LQI_LOW", "50")),
        device_stale_hours=int(os.getenv("HEMS_DEVICE_STALE_HOURS", "24")),
        gpu_type=os.getenv("GPU_TYPE", "none"),
        gpu_high_load_threshold=int(os.getenv("GPU_HIGH_LOAD_THRESHOLD", "80")),
        soil_moisture_low=float(os.getenv("HEMS_THRESHOLD_SOIL_LOW", "25")),
        auto_water_enabled=_env_bool("HEMS_ENABLE_AUTO_WATER", False),
        auto_water_duration_s=min(int(os.getenv("HEMS_AUTO_WATER_DURATION_S", "45")), 45),
        voc_high_threshold=float(os.getenv("HEMS_THRESHOLD_VOC_HIGH", "500")),
        voc_sustain_seconds=int(os.getenv("HEMS_VOC_SUSTAIN_SECONDS", "120")),
        voc_cooldown_seconds=int(os.getenv("HEMS_VOC_COOLDOWN_SECONDS", "1800")),
        pm25_native_high=_pm25_native_default(),
        low_pressure_threshold=float(os.getenv("HEMS_THRESHOLD_PRESSURE_LOW", "1000")),
        low_pressure_sustain_s=int(os.getenv("HEMS_PRESSURE_LOW_SUSTAIN_S", str(3 * 3600))),
        illuminance_low_lx=float(os.getenv("HEMS_THRESHOLD_LIGHT_LOW", "20")),
        illuminance_low_sustain_s=int(os.getenv("HEMS_LIGHT_LOW_SUSTAIN_S", "600")),
        illuminance_high_lx=float(os.getenv("HEMS_THRESHOLD_LIGHT_HIGH", "50000")),
        illuminance_high_sustain_s=int(os.getenv("HEMS_LIGHT_HIGH_SUSTAIN_S", "600")),
        absence_lighting_enabled=_env_bool("HEMS_ABSENCE_LIGHTING_ENABLED", True),
        absence_lighting_interval=int(os.getenv("HEMS_ABSENCE_LIGHTING_INTERVAL", "1800")),
        absence_lighting_start_hour=int(os.getenv("HEMS_ABSENCE_LIGHTING_HOURS_START", "17")),
        absence_lighting_end_hour=int(os.getenv("HEMS_ABSENCE_LIGHTING_HOURS_END", "23")),
        circadian_enabled=_env_bool("HEMS_CIRCADIAN_ENABLED", True),
        circadian_interval=int(os.getenv("HEMS_CIRCADIAN_INTERVAL", "1800")),
        circadian_curve=[
            (0, 450, 30),
            (6, 400, 50),
            (8, 270, 100),
            (12, 250, 100),
            (17, 300, 100),
            (20, 380, 80),
            (22, 430, 50),
        ],
    )
