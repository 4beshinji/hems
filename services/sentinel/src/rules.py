"""
HEMS Lite Sentinel — rule engine.
Clear threshold violations → deterministic alerts (no LLM needed).
"""
import time
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from config import (
    HR_CRITICAL_HIGH, HR_CRITICAL_LOW, SPO2_CRITICAL,
    HR_HIGH, HR_LOW, SPO2_LOW, STRESS_HIGH, BODY_TEMP_HIGH,
    RESPIRATORY_RATE_HIGH, HRV_LOW,
    SEDENTARY_ALERT_MINUTES, FATIGUE_HIGH,
    TEMP_HIGH, TEMP_LOW, TEMP_WARN_HIGH, TEMP_WARN_LOW,
    HUMIDITY_HIGH, HUMIDITY_LOW, CO2_HIGH, CO2_CRITICAL,
    ABSENCE_ALERT_MINUTES, NIGHT_ACTIVITY_START, NIGHT_ACTIVITY_END,
    LYING_DAYTIME_MINUTES,
    COOLDOWN_CRITICAL, COOLDOWN_HIGH, COOLDOWN_NORMAL, COOLDOWN_INFO,
)
from state import OccupantState


class AlertLevel(IntEnum):
    INFO = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Alert:
    level: AlertLevel
    rule_id: str
    title: str
    body: str
    source: str          # biometric | activity | environment
    zone: str = ""
    data: dict | None = None


def _parse_time(s: str) -> tuple[int, int]:
    parts = s.split(":")
    return int(parts[0]), int(parts[1])


NIGHT_START_H, NIGHT_START_M = _parse_time(NIGHT_ACTIVITY_START)
NIGHT_END_H, NIGHT_END_M = _parse_time(NIGHT_ACTIVITY_END)


class RuleEngine:
    """Evaluates clear threshold violations. Returns deterministic alerts."""

    def __init__(self):
        self._cooldowns: dict[str, float] = {}

    def evaluate(self, state: OccupantState) -> list[Alert]:
        """Run all rules against current state. Returns fired alerts."""
        alerts: list[Alert] = []
        alerts.extend(self._evaluate_biometric_critical(state))
        alerts.extend(self._evaluate_biometric_high(state))
        alerts.extend(self._evaluate_biometric_normal(state))
        alerts.extend(self._evaluate_activity(state))
        alerts.extend(self._evaluate_environment(state))
        alerts.extend(self._evaluate_info(state))
        return alerts

    # --- CRITICAL (immediate, no cooldown) ---

    def _evaluate_biometric_critical(self, s: OccupantState) -> list[Alert]:
        alerts = []

        if s.spo2.is_fresh and s.spo2.value is not None and s.spo2.value < SPO2_CRITICAL:
            if self._check(f"C1_spo2", COOLDOWN_CRITICAL):
                alerts.append(Alert(
                    level=AlertLevel.CRITICAL, rule_id="C1",
                    title="血中酸素が危険レベル",
                    body=f"SpO2が{s.spo2.value:.0f}%です（閾値: {SPO2_CRITICAL}%）。"
                         "直ちに確認してください。",
                    source="biometric",
                    data={"spo2": s.spo2.value},
                ))

        if s.heart_rate.is_fresh and s.heart_rate.value is not None:
            if s.heart_rate.value < HR_CRITICAL_LOW:
                if self._check("C2_hr_low", COOLDOWN_CRITICAL):
                    alerts.append(Alert(
                        level=AlertLevel.CRITICAL, rule_id="C2",
                        title="心拍数が危険に低下",
                        body=f"心拍数が{s.heart_rate.value:.0f}bpmです（閾値: {HR_CRITICAL_LOW}bpm）。",
                        source="biometric",
                        data={"hr": s.heart_rate.value},
                    ))
            elif s.heart_rate.value > HR_CRITICAL_HIGH:
                if self._check("C3_hr_high", COOLDOWN_CRITICAL):
                    alerts.append(Alert(
                        level=AlertLevel.CRITICAL, rule_id="C3",
                        title="心拍数が危険に上昇",
                        body=f"心拍数が{s.heart_rate.value:.0f}bpmです（閾値: {HR_CRITICAL_HIGH}bpm）。",
                        source="biometric",
                        data={"hr": s.heart_rate.value},
                    ))

        # C4: Fall detection (lying + sudden activity drop)
        if (s.activity.posture == "lying"
                and s.activity.activity_level < 0.05
                and s.activity.posture_duration_sec < 120
                and s.activity.person_count > 0):
            # Recently transitioned to lying with very low activity
            hist = s.get_history("activity_" + (next(iter(s.zones), "home")), hours=1)
            if len(hist) >= 2:
                recent_high = any(v > 0.3 for _, v in hist[-10:])
                if recent_high and self._check("C4_fall", COOLDOWN_CRITICAL):
                    alerts.append(Alert(
                        level=AlertLevel.CRITICAL, rule_id="C4",
                        title="転倒の可能性",
                        body="急に横になり、動きが止まりました。転倒の可能性があります。",
                        source="activity",
                        data={"posture": "lying", "activity_level": s.activity.activity_level},
                    ))

        # C5: Prolonged absence (expected home but no detection)
        if (s.activity.person_count == 0
                and s.activity.timestamp > 0
                and s.activity.posture_duration_sec > ABSENCE_ALERT_MINUTES * 60):
            if self._check("C5_absence", COOLDOWN_HIGH):  # 5min cooldown for absence
                alerts.append(Alert(
                    level=AlertLevel.CRITICAL, rule_id="C5",
                    title="長時間不検知",
                    body=f"{ABSENCE_ALERT_MINUTES}分以上、人が検知されていません。",
                    source="activity",
                    data={"absence_minutes": ABSENCE_ALERT_MINUTES},
                ))

        return alerts

    # --- HIGH (5min cooldown) ---

    def _evaluate_biometric_high(self, s: OccupantState) -> list[Alert]:
        alerts = []

        if s.spo2.is_fresh and s.spo2.value is not None:
            if SPO2_CRITICAL <= s.spo2.value < SPO2_LOW:
                if self._check("H1_spo2", COOLDOWN_HIGH):
                    alerts.append(Alert(
                        level=AlertLevel.HIGH, rule_id="H1",
                        title="血中酸素が低下",
                        body=f"SpO2が{s.spo2.value:.0f}%です（閾値: {SPO2_LOW}%）。",
                        source="biometric",
                        data={"spo2": s.spo2.value},
                    ))

        if s.heart_rate.is_fresh and s.heart_rate.value is not None:
            if HR_HIGH < s.heart_rate.value <= HR_CRITICAL_HIGH:
                if self._check("H2_hr_high", COOLDOWN_HIGH):
                    alerts.append(Alert(
                        level=AlertLevel.HIGH, rule_id="H2",
                        title="心拍数上昇",
                        body=f"心拍数が{s.heart_rate.value:.0f}bpmです（閾値: {HR_HIGH}bpm）。",
                        source="biometric",
                        data={"hr": s.heart_rate.value},
                    ))
            elif HR_CRITICAL_LOW <= s.heart_rate.value < HR_LOW:
                if self._check("H3_hr_low", COOLDOWN_HIGH):
                    alerts.append(Alert(
                        level=AlertLevel.HIGH, rule_id="H3",
                        title="心拍数低め",
                        body=f"心拍数が{s.heart_rate.value:.0f}bpmです（閾値: {HR_LOW}bpm）。",
                        source="biometric",
                        data={"hr": s.heart_rate.value},
                    ))

        # H4: Extreme room temperature
        for zid, zone in s.zones.items():
            env = zone.environment
            if env.temperature is not None:
                if env.temperature > TEMP_HIGH:
                    if self._check(f"H4_temp_high_{zid}", COOLDOWN_HIGH):
                        alerts.append(Alert(
                            level=AlertLevel.HIGH, rule_id="H4",
                            title=f"室温危険 ({zid})",
                            body=f"室温が{env.temperature:.1f}度です（閾値: {TEMP_HIGH}度）。"
                                 "熱中症に注意してください。",
                            source="environment", zone=zid,
                            data={"temperature": env.temperature},
                        ))
                elif env.temperature < TEMP_LOW:
                    if self._check(f"H4_temp_low_{zid}", COOLDOWN_HIGH):
                        alerts.append(Alert(
                            level=AlertLevel.HIGH, rule_id="H4",
                            title=f"室温危険 ({zid})",
                            body=f"室温が{env.temperature:.1f}度です（閾値: {TEMP_LOW}度）。"
                                 "低体温症に注意してください。",
                            source="environment", zone=zid,
                            data={"temperature": env.temperature},
                        ))

        # H5: Night activity
        now = datetime.now()
        night_start = now.replace(hour=NIGHT_START_H, minute=NIGHT_START_M)
        night_end = now.replace(hour=NIGHT_END_H, minute=NIGHT_END_M)
        is_night = night_start <= now <= night_end if NIGHT_START_H < NIGHT_END_H else (
            now >= night_start or now <= night_end
        )
        if (is_night
                and s.activity.posture == "walking"
                and s.activity.person_count > 0):
            if self._check("H5_night_walk", COOLDOWN_HIGH):
                alerts.append(Alert(
                    level=AlertLevel.HIGH, rule_id="H5",
                    title="深夜の活動検知",
                    body=f"深夜{now.strftime('%H:%M')}に歩行を検知しました。",
                    source="activity",
                    data={"posture": "walking", "time": now.isoformat()},
                ))

        # H6: Prolonged lying (daytime, 3h+)
        hour = now.hour
        if (6 <= hour <= 21
                and s.activity.posture == "lying"
                and s.activity.posture_duration_sec > LYING_DAYTIME_MINUTES * 60
                and s.activity.person_count > 0):
            if self._check("H6_lying_long", COOLDOWN_HIGH):
                dur_h = s.activity.posture_duration_sec / 3600
                alerts.append(Alert(
                    level=AlertLevel.HIGH, rule_id="H6",
                    title="長時間臥位",
                    body=f"日中に{dur_h:.1f}時間横になっています。",
                    source="activity",
                    data={"posture": "lying", "duration_hours": dur_h},
                ))

        # H7: Body temp high
        if (s.body_temp.is_fresh and s.body_temp.value is not None
                and s.body_temp.value > BODY_TEMP_HIGH):
            if self._check("H7_body_temp", COOLDOWN_HIGH):
                alerts.append(Alert(
                    level=AlertLevel.HIGH, rule_id="H7",
                    title="体温上昇",
                    body=f"体温が{s.body_temp.value:.1f}度です（閾値: {BODY_TEMP_HIGH}度）。",
                    source="biometric",
                    data={"body_temp": s.body_temp.value},
                ))

        # H8: Respiratory rate high
        if (s.respiratory_rate.is_fresh and s.respiratory_rate.value is not None
                and s.respiratory_rate.value > RESPIRATORY_RATE_HIGH):
            if self._check("H8_resp_high", COOLDOWN_HIGH):
                alerts.append(Alert(
                    level=AlertLevel.HIGH, rule_id="H8",
                    title="呼吸数上昇",
                    body=f"呼吸数が{s.respiratory_rate.value:.0f}回/分です"
                         f"（閾値: {RESPIRATORY_RATE_HIGH}回/分）。",
                    source="biometric",
                    data={"respiratory_rate": s.respiratory_rate.value},
                ))

        return alerts

    # --- NORMAL (30min cooldown) ---

    def _evaluate_biometric_normal(self, s: OccupantState) -> list[Alert]:
        alerts = []

        if (s.stress.is_fresh and s.stress.value is not None
                and s.stress.value > STRESS_HIGH):
            if self._check("N_stress", COOLDOWN_NORMAL):
                alerts.append(Alert(
                    level=AlertLevel.NORMAL, rule_id="N2",
                    title="ストレス高め",
                    body=f"ストレスレベルが{s.stress.value:.0f}です（閾値: {STRESS_HIGH}）。",
                    source="biometric",
                    data={"stress": s.stress.value},
                ))

        if (s.fatigue.is_fresh and s.fatigue.value is not None
                and s.fatigue.value > FATIGUE_HIGH):
            if self._check("N_fatigue", COOLDOWN_NORMAL):
                alerts.append(Alert(
                    level=AlertLevel.NORMAL, rule_id="N_fatigue",
                    title="疲労蓄積",
                    body=f"疲労スコアが{s.fatigue.value:.0f}です（閾値: {FATIGUE_HIGH}）。"
                         "休息を取りましょう。",
                    source="biometric",
                    data={"fatigue": s.fatigue.value},
                ))

        if (s.hrv.is_fresh and s.hrv.value is not None
                and s.hrv.value < HRV_LOW):
            if self._check("N_hrv_low", COOLDOWN_NORMAL):
                alerts.append(Alert(
                    level=AlertLevel.NORMAL, rule_id="N_hrv",
                    title="HRV低下",
                    body=f"HRVが{s.hrv.value:.0f}msです（閾値: {HRV_LOW}ms）。"
                         "自律神経の疲労が出ています。",
                    source="biometric",
                    data={"hrv": s.hrv.value},
                ))

        return alerts

    def _evaluate_activity(self, s: OccupantState) -> list[Alert]:
        alerts = []

        # N1: Sedentary
        if (s.activity.posture == "sitting"
                and s.activity.posture_duration_sec > SEDENTARY_ALERT_MINUTES * 60
                and s.activity.person_count > 0):
            if self._check("N1_sedentary", COOLDOWN_NORMAL):
                dur = int(s.activity.posture_duration_sec / 60)
                alerts.append(Alert(
                    level=AlertLevel.NORMAL, rule_id="N1",
                    title="長時間座位",
                    body=f"{dur}分座りっぱなしです。少し体を動かしましょう。",
                    source="activity",
                    data={"posture_minutes": dur},
                ))

        return alerts

    def _evaluate_environment(self, s: OccupantState) -> list[Alert]:
        alerts = []

        for zid, zone in s.zones.items():
            env = zone.environment

            # CO2 critical
            if env.co2 is not None and env.co2 > CO2_CRITICAL:
                if self._check(f"env_co2_crit_{zid}", COOLDOWN_HIGH):
                    alerts.append(Alert(
                        level=AlertLevel.HIGH, rule_id="env_co2_crit",
                        title=f"CO2危険 ({zid})",
                        body=f"CO2が{env.co2:.0f}ppmです。直ちに換気してください。",
                        source="environment", zone=zid,
                        data={"co2": env.co2},
                    ))
            elif env.co2 is not None and env.co2 > CO2_HIGH:
                if self._check(f"env_co2_high_{zid}", COOLDOWN_NORMAL):
                    alerts.append(Alert(
                        level=AlertLevel.NORMAL, rule_id="env_co2_high",
                        title=f"CO2上昇 ({zid})",
                        body=f"CO2が{env.co2:.0f}ppmです。換気しましょう。",
                        source="environment", zone=zid,
                        data={"co2": env.co2},
                    ))

            # Humidity
            if env.humidity is not None:
                if env.humidity > HUMIDITY_HIGH:
                    if self._check(f"env_hum_high_{zid}", COOLDOWN_NORMAL):
                        alerts.append(Alert(
                            level=AlertLevel.NORMAL, rule_id="env_humidity",
                            title=f"湿度が高い ({zid})",
                            body=f"湿度が{env.humidity:.0f}%です。除湿しましょう。",
                            source="environment", zone=zid,
                        ))
                elif env.humidity < HUMIDITY_LOW:
                    if self._check(f"env_hum_low_{zid}", COOLDOWN_NORMAL):
                        alerts.append(Alert(
                            level=AlertLevel.NORMAL, rule_id="env_humidity",
                            title=f"湿度が低い ({zid})",
                            body=f"湿度が{env.humidity:.0f}%です。加湿しましょう。",
                            source="environment", zone=zid,
                        ))

            # Temperature warnings (not critical)
            if env.temperature is not None:
                if TEMP_WARN_HIGH < env.temperature <= TEMP_HIGH:
                    if self._check(f"env_temp_warn_high_{zid}", COOLDOWN_NORMAL):
                        alerts.append(Alert(
                            level=AlertLevel.NORMAL, rule_id="env_temp_warn",
                            title=f"室温やや高め ({zid})",
                            body=f"室温が{env.temperature:.1f}度です。エアコンの使用を検討してください。",
                            source="environment", zone=zid,
                        ))
                elif TEMP_LOW <= env.temperature < TEMP_WARN_LOW:
                    if self._check(f"env_temp_warn_low_{zid}", COOLDOWN_NORMAL):
                        alerts.append(Alert(
                            level=AlertLevel.NORMAL, rule_id="env_temp_warn",
                            title=f"室温やや低め ({zid})",
                            body=f"室温が{env.temperature:.1f}度です。暖房の使用を検討してください。",
                            source="environment", zone=zid,
                        ))

        return alerts

    # --- INFO (daily summary only) ---

    def _evaluate_info(self, s: OccupantState) -> list[Alert]:
        alerts = []

        # Sleep duration anomaly
        if s.sleep.timestamp > 0 and s.sleep.duration_hours > 0:
            if s.sleep.duration_hours < 5:
                if self._check("I1_short_sleep", COOLDOWN_INFO):
                    alerts.append(Alert(
                        level=AlertLevel.INFO, rule_id="I1",
                        title="睡眠不足",
                        body=f"睡眠時間が{s.sleep.duration_hours:.1f}時間でした。",
                        source="biometric",
                    ))
            elif s.sleep.duration_hours > 11:
                if self._check("I1_long_sleep", COOLDOWN_INFO):
                    alerts.append(Alert(
                        level=AlertLevel.INFO, rule_id="I1",
                        title="睡眠過多",
                        body=f"睡眠時間が{s.sleep.duration_hours:.1f}時間でした。",
                        source="biometric",
                    ))

        # Low step count (end of day check)
        hour = datetime.now().hour
        if (hour >= 20
                and s.activity.steps > 0
                and s.activity.steps < 1000):
            if self._check("I2_low_steps", COOLDOWN_INFO):
                alerts.append(Alert(
                    level=AlertLevel.INFO, rule_id="I2",
                    title="活動量少なめ",
                    body=f"本日の歩数は{s.activity.steps}歩です。",
                    source="activity",
                ))

        # Sleep quality
        if (s.sleep.quality_score > 0 and s.sleep.quality_score < 40):
            if self._check("I3_sleep_quality", COOLDOWN_INFO):
                alerts.append(Alert(
                    level=AlertLevel.INFO, rule_id="I3",
                    title="睡眠品質低下",
                    body=f"睡眠品質スコアが{s.sleep.quality_score}点でした。",
                    source="biometric",
                ))

        return alerts

    def _check(self, key: str, cooldown: float) -> bool:
        """Check cooldown. Returns True if action allowed."""
        now = time.time()
        last = self._cooldowns.get(key, 0)
        if cooldown > 0 and now - last < cooldown:
            return False
        self._cooldowns[key] = now
        return True
