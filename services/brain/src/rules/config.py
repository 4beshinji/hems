"""Configuration for RuleEngine facade and domain mixins."""

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).lower() == "true"


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


def load_rule_thresholds() -> RuleThresholds:
    return RuleThresholds(
        temp_critical_high=float(os.getenv("HEMS_THRESHOLD_TEMP_CRITICAL_HIGH", "40.0")),
        temp_critical_low=float(os.getenv("HEMS_THRESHOLD_TEMP_CRITICAL_LOW", "5.0")),
        spo2_critical_low=int(os.getenv("HEMS_THRESHOLD_SPO2_CRITICAL_LOW", "88")),
        hr_critical_sleep=int(os.getenv("HEMS_THRESHOLD_HR_CRITICAL_SLEEP", "150")),
        biometric_stale_minutes=int(os.getenv("HEMS_BIOMETRIC_STALE_MINUTES", "30")),
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
        pm25_native_high=float(os.getenv("HEMS_THRESHOLD_PM25_NATIVE", "35")),
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
