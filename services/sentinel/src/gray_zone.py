"""
HEMS Lite Sentinel — gray zone detector.
Identifies ambiguous situations that rules can't handle deterministically.
These are escalated to an LLM for judgment.
"""
import time
from dataclasses import dataclass, field
from datetime import datetime

from config import (
    GRAY_ZONE_FACTOR, GRAY_ZONE_MIN_SIGNALS,
    TREND_WINDOW_HOURS, PATTERN_DEVIATION_MINUTES,
    HR_HIGH, HR_LOW, SPO2_LOW, STRESS_HIGH,
    FATIGUE_HIGH, SEDENTARY_ALERT_MINUTES,
    TEMP_WARN_HIGH, TEMP_WARN_LOW,
    COOLDOWN_GRAY_ZONE,
)
from state import OccupantState


@dataclass
class GrayZoneEvent:
    """An ambiguous situation that needs LLM judgment."""
    pattern: str          # compound_anomaly | behavior_deviation | trend | contradiction | sensor_gap
    description: str      # Human-readable summary
    signals: list[str]    # List of contributing signals
    confidence: float     # 0.0-1.0, how concerning this is
    data: dict = field(default_factory=dict)


class GrayZoneDetector:
    """Detects ambiguous patterns below clear thresholds."""

    def __init__(self):
        self._cooldowns: dict[str, float] = {}
        # Learned behavior patterns (updated over time)
        self._wake_times: list[float] = []   # hour-of-day floats
        self._sleep_times: list[float] = []
        self._activity_baseline: float = 0.0
        self._hr_baseline: float = 0.0
        self._hr_baseline_count: int = 0

    def evaluate(self, state: OccupantState) -> list[GrayZoneEvent]:
        """Detect gray zone situations. Returns events for LLM escalation."""
        events: list[GrayZoneEvent] = []

        compound = self._check_compound_anomaly(state)
        if compound:
            events.append(compound)

        trend = self._check_trends(state)
        if trend:
            events.append(trend)

        contradiction = self._check_contradictions(state)
        if contradiction:
            events.append(contradiction)

        gap = self._check_sensor_gap(state)
        if gap:
            events.append(gap)

        deviation = self._check_behavior_deviation(state)
        if deviation:
            events.append(deviation)

        # Update baselines
        self._update_baselines(state)

        return events

    def _check_compound_anomaly(self, s: OccupantState) -> GrayZoneEvent | None:
        """Multiple sub-threshold readings that are individually OK but collectively concerning."""
        if not self._check_cooldown("compound"):
            return None

        signals = []
        total_concern = 0.0

        # Each metric: if above GRAY_ZONE_FACTOR * threshold, it's a "warm" signal
        if s.heart_rate.is_fresh and s.heart_rate.value is not None:
            ratio = s.heart_rate.value / HR_HIGH
            if ratio >= GRAY_ZONE_FACTOR and s.heart_rate.value <= HR_HIGH:
                signals.append(f"HR={s.heart_rate.value:.0f}bpm (閾値の{ratio:.0%})")
                total_concern += ratio

        if s.stress.is_fresh and s.stress.value is not None:
            ratio = s.stress.value / STRESS_HIGH
            if ratio >= GRAY_ZONE_FACTOR and s.stress.value <= STRESS_HIGH:
                signals.append(f"stress={s.stress.value:.0f} (閾値の{ratio:.0%})")
                total_concern += ratio

        if s.fatigue.is_fresh and s.fatigue.value is not None:
            ratio = s.fatigue.value / FATIGUE_HIGH
            if ratio >= GRAY_ZONE_FACTOR and s.fatigue.value <= FATIGUE_HIGH:
                signals.append(f"fatigue={s.fatigue.value:.0f} (閾値の{ratio:.0%})")
                total_concern += ratio

        if s.spo2.is_fresh and s.spo2.value is not None:
            # SpO2 is inverted (lower = worse)
            if SPO2_LOW <= s.spo2.value <= SPO2_LOW + 3:
                signals.append(f"SpO2={s.spo2.value:.0f}% (閾値付近)")
                total_concern += 0.8

        if s.hrv.is_fresh and s.hrv.value is not None:
            from config import HRV_LOW
            if s.hrv.value < HRV_LOW * 1.5 and s.hrv.value >= HRV_LOW:
                signals.append(f"HRV={s.hrv.value:.0f}ms (低め)")
                total_concern += 0.7

        # Sedentary adds to compound
        if (s.activity.posture == "sitting"
                and s.activity.posture_duration_sec > SEDENTARY_ALERT_MINUTES * 60 * GRAY_ZONE_FACTOR):
            dur = int(s.activity.posture_duration_sec / 60)
            signals.append(f"座位{dur}分")
            total_concern += 0.6

        if len(signals) >= GRAY_ZONE_MIN_SIGNALS:
            confidence = min(total_concern / len(signals), 1.0)
            return GrayZoneEvent(
                pattern="compound_anomaly",
                description=f"複数の指標が閾値付近: {', '.join(signals)}",
                signals=signals,
                confidence=confidence,
                data={
                    "hr": s.heart_rate.value,
                    "stress": s.stress.value if s.stress.is_fresh else None,
                    "fatigue": s.fatigue.value if s.fatigue.is_fresh else None,
                    "spo2": s.spo2.value if s.spo2.is_fresh else None,
                },
            )
        return None

    def _check_trends(self, s: OccupantState) -> GrayZoneEvent | None:
        """Gradual worsening trends over hours."""
        if not self._check_cooldown("trend"):
            return None

        signals = []

        # HR trend: rising over past hours
        hr_hist = s.get_history("bio_heart_rate", TREND_WINDOW_HOURS)
        if len(hr_hist) >= 6:  # need enough data points
            early = [v for _, v in hr_hist[:len(hr_hist) // 3]]
            late = [v for _, v in hr_hist[-(len(hr_hist) // 3):]]
            if early and late:
                early_avg = sum(early) / len(early)
                late_avg = sum(late) / len(late)
                if late_avg > early_avg * 1.15:  # 15% increase
                    signals.append(
                        f"HR上昇傾向: {early_avg:.0f}→{late_avg:.0f}bpm "
                        f"(過去{TREND_WINDOW_HOURS}h)"
                    )

        # SpO2 trend: declining
        spo2_hist = s.get_history("bio_spo2", TREND_WINDOW_HOURS)
        if len(spo2_hist) >= 6:
            early = [v for _, v in spo2_hist[:len(spo2_hist) // 3]]
            late = [v for _, v in spo2_hist[-(len(spo2_hist) // 3):]]
            if early and late:
                early_avg = sum(early) / len(early)
                late_avg = sum(late) / len(late)
                if late_avg < early_avg - 2:  # 2% drop
                    signals.append(
                        f"SpO2低下傾向: {early_avg:.0f}→{late_avg:.0f}% "
                        f"(過去{TREND_WINDOW_HOURS}h)"
                    )

        # Stress trend: consistently rising
        stress_hist = s.get_history("bio_stress", TREND_WINDOW_HOURS)
        if len(stress_hist) >= 6:
            early = [v for _, v in stress_hist[:len(stress_hist) // 3]]
            late = [v for _, v in stress_hist[-(len(stress_hist) // 3):]]
            if early and late:
                early_avg = sum(early) / len(early)
                late_avg = sum(late) / len(late)
                if late_avg > early_avg * 1.3:
                    signals.append(
                        f"ストレス上昇傾向: {early_avg:.0f}→{late_avg:.0f} "
                        f"(過去{TREND_WINDOW_HOURS}h)"
                    )

        if signals:
            return GrayZoneEvent(
                pattern="trend",
                description=f"緩やかな悪化傾向: {'; '.join(signals)}",
                signals=signals,
                confidence=0.6,
            )
        return None

    def _check_contradictions(self, s: OccupantState) -> GrayZoneEvent | None:
        """Contradictory sensor signals."""
        if not self._check_cooldown("contradiction"):
            return None

        signals = []

        # Lying + high HR + daytime = concerning
        hour = datetime.now().hour
        if (6 <= hour <= 22
                and s.activity.posture == "lying"
                and s.heart_rate.is_fresh
                and s.heart_rate.value is not None
                and s.heart_rate.value > 90):
            signals.append(
                f"日中臥位 + HR={s.heart_rate.value:.0f}bpm"
            )

        # High activity level + low HR (sensor malfunction or concerning)
        if (s.activity.activity_level > 0.5
                and s.heart_rate.is_fresh
                and s.heart_rate.value is not None
                and s.heart_rate.value < 55):
            signals.append(
                f"高活動(level={s.activity.activity_level:.1f}) + "
                f"低HR={s.heart_rate.value:.0f}bpm"
            )

        # Person detected but no biometric data for >30min
        if (s.activity.person_count > 0
                and s.activity.timestamp > 0
                and s.heart_rate.timestamp > 0
                and s.heart_rate.age_seconds > 1800):
            signals.append(
                f"在室中だがバイタル{s.heart_rate.age_seconds / 60:.0f}分途絶"
            )

        if signals:
            return GrayZoneEvent(
                pattern="contradiction",
                description=f"矛盾シグナル: {'; '.join(signals)}",
                signals=signals,
                confidence=0.7,
            )
        return None

    def _check_sensor_gap(self, s: OccupantState) -> GrayZoneEvent | None:
        """Missing sensor data when occupant is expected to be present."""
        if not self._check_cooldown("sensor_gap"):
            return None

        now = time.time()
        signals = []

        # Biometric bridge was connected but data stopped
        if s.biometric_connected and s.heart_rate.timestamp > 0:
            gap_min = (now - s.heart_rate.timestamp) / 60
            if gap_min > 30:
                signals.append(f"バイタルデータ{gap_min:.0f}分途絶")

        # Perception was connected but data stopped
        if s.perception_connected and s.activity.timestamp > 0:
            gap_min = (now - s.activity.timestamp) / 60
            if gap_min > 10:
                signals.append(f"カメラデータ{gap_min:.0f}分途絶")

        if signals:
            return GrayZoneEvent(
                pattern="sensor_gap",
                description=f"センサーデータ欠落: {'; '.join(signals)}",
                signals=signals,
                confidence=0.5,
                data={"biometric_age_s": s.heart_rate.age_seconds,
                      "activity_age_s": now - s.activity.timestamp if s.activity.timestamp > 0 else 0},
            )
        return None

    def _check_behavior_deviation(self, s: OccupantState) -> GrayZoneEvent | None:
        """Deviation from learned daily patterns."""
        if not self._check_cooldown("behavior_dev"):
            return None

        signals = []
        now = datetime.now()
        hour_f = now.hour + now.minute / 60.0

        # Wake time deviation: if usually up by X but still lying
        if (self._wake_times and len(self._wake_times) >= 3
                and s.activity.posture == "lying"
                and s.activity.person_count > 0):
            avg_wake = sum(self._wake_times) / len(self._wake_times)
            if hour_f > avg_wake + PATTERN_DEVIATION_MINUTES / 60:
                signals.append(
                    f"通常{avg_wake:.1f}時に起床だが{hour_f:.1f}時も臥位"
                )

        # Baseline HR deviation
        if (self._hr_baseline > 0 and self._hr_baseline_count >= 20
                and s.heart_rate.is_fresh and s.heart_rate.value is not None):
            deviation = abs(s.heart_rate.value - self._hr_baseline)
            if deviation > self._hr_baseline * 0.25:  # >25% from baseline
                signals.append(
                    f"HR基準値{self._hr_baseline:.0f}から"
                    f"{deviation:.0f}bpm乖離"
                )

        if signals:
            return GrayZoneEvent(
                pattern="behavior_deviation",
                description=f"行動パターン逸脱: {'; '.join(signals)}",
                signals=signals,
                confidence=0.5,
            )
        return None

    def _update_baselines(self, s: OccupantState):
        """Update learned behavior baselines."""
        # Track wake times (transition from lying/sleep to standing/walking at 5-12h)
        hour = datetime.now().hour
        if (5 <= hour <= 12
                and s.activity.posture in ("standing", "walking")
                and s.sleep.stage == "awake"):
            hour_f = hour + datetime.now().minute / 60.0
            if not self._wake_times or abs(self._wake_times[-1] - hour_f) > 0.5:
                self._wake_times.append(hour_f)
                if len(self._wake_times) > 14:  # 2 weeks rolling
                    self._wake_times = self._wake_times[-14:]

        # Update HR baseline (rolling average of resting HR)
        if (s.heart_rate.is_fresh
                and s.heart_rate.value is not None
                and s.activity.posture in ("sitting", "lying")
                and s.activity.activity_level < 0.2
                and 50 < s.heart_rate.value < 100):
            # Exponential moving average
            if self._hr_baseline <= 0:
                self._hr_baseline = s.heart_rate.value
            else:
                alpha = 0.05  # slow adaptation
                self._hr_baseline = alpha * s.heart_rate.value + (1 - alpha) * self._hr_baseline
            self._hr_baseline_count += 1

    def _check_cooldown(self, key: str) -> bool:
        now = time.time()
        last = self._cooldowns.get(key, 0)
        if now - last < COOLDOWN_GRAY_ZONE:
            return False
        self._cooldowns[key] = now
        return True
