"""
Data normalization and fatigue score calculation for biometric data.
"""
from dataclasses import dataclass, field
from typing import Optional
import time
from loguru import logger

from config import FATIGUE_HR_WEIGHT, FATIGUE_SLEEP_WEIGHT, FATIGUE_STRESS_WEIGHT


@dataclass
class BiometricReading:
    """Normalized biometric reading from any provider."""
    timestamp: float = field(default_factory=time.time)
    heart_rate: Optional[int] = None
    resting_heart_rate: Optional[int] = None
    spo2: Optional[int] = None
    steps: Optional[int] = None
    steps_goal: Optional[int] = None
    calories: Optional[int] = None
    active_minutes: Optional[int] = None
    activity_level: Optional[str] = None  # rest | light | moderate | vigorous
    stress_level: Optional[int] = None  # 0-100
    sleep_stage: Optional[str] = None  # awake | light | deep | rem
    sleep_duration_minutes: Optional[int] = None
    sleep_deep_minutes: Optional[int] = None
    sleep_rem_minutes: Optional[int] = None
    sleep_light_minutes: Optional[int] = None
    sleep_quality_score: Optional[int] = None
    sleep_start_ts: Optional[float] = None
    sleep_end_ts: Optional[float] = None
    provider: str = ""


class DataProcessor:
    """Normalizes and computes derived biometric metrics."""

    def __init__(self):
        self._latest: Optional[BiometricReading] = None
        self._sleep_cache: Optional[dict] = None
        self._hr_history: list[int] = []  # last N heart rate readings
        self._max_hr_history = 60

    def process(self, reading: BiometricReading) -> BiometricReading:
        """Normalize and enrich a biometric reading."""
        if reading.heart_rate is not None:
            self._hr_history.append(reading.heart_rate)
            if len(self._hr_history) > self._max_hr_history:
                self._hr_history = self._hr_history[-self._max_hr_history:]

        self._latest = reading
        return reading

    def get_latest(self) -> Optional[BiometricReading]:
        return self._latest

    def get_sleep_summary(self) -> Optional[dict]:
        return self._sleep_cache

    def update_sleep_summary(self, reading: BiometricReading):
        """Cache sleep summary from overnight data."""
        if reading.sleep_duration_minutes and reading.sleep_duration_minutes > 0:
            self._sleep_cache = {
                "duration_minutes": reading.sleep_duration_minutes,
                "deep_minutes": reading.sleep_deep_minutes or 0,
                "rem_minutes": reading.sleep_rem_minutes or 0,
                "light_minutes": reading.sleep_light_minutes or 0,
                "quality_score": reading.sleep_quality_score or 0,
                "sleep_start_ts": reading.sleep_start_ts or 0,
                "sleep_end_ts": reading.sleep_end_ts or 0,
            }

    def compute_fatigue(self) -> dict:
        """Compute fatigue score from available data."""
        factors = []
        score = 0.0
        weight_total = 0.0

        # HR component: sustained high HR → fatigue
        if self._hr_history:
            avg_hr = sum(self._hr_history) / len(self._hr_history)
            if avg_hr > 100:
                hr_fatigue = min((avg_hr - 60) / 100 * 100, 100)
                score += hr_fatigue * FATIGUE_HR_WEIGHT
                weight_total += FATIGUE_HR_WEIGHT
                factors.append("elevated_heart_rate")
            elif avg_hr > 0:
                hr_fatigue = max(0, (avg_hr - 60) / 100 * 100)
                score += hr_fatigue * FATIGUE_HR_WEIGHT
                weight_total += FATIGUE_HR_WEIGHT

        # Sleep component: poor sleep → fatigue
        if self._sleep_cache:
            quality = self._sleep_cache.get("quality_score", 50)
            sleep_fatigue = max(0, 100 - quality)
            score += sleep_fatigue * FATIGUE_SLEEP_WEIGHT
            weight_total += FATIGUE_SLEEP_WEIGHT
            if quality < 50:
                factors.append("poor_sleep")

        # Stress component
        if self._latest and self._latest.stress_level is not None:
            stress_fatigue = self._latest.stress_level
            score += stress_fatigue * FATIGUE_STRESS_WEIGHT
            weight_total += FATIGUE_STRESS_WEIGHT
            if self._latest.stress_level > 70:
                factors.append("high_stress")

        if weight_total > 0:
            fatigue_score = int(score / weight_total)
        else:
            fatigue_score = 0

        return {"score": min(fatigue_score, 100), "factors": factors}
