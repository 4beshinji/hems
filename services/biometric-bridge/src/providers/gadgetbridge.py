"""
Gadgetbridge webhook provider — receives POST data from Gadgetbridge app
(via Tasker/Automate or direct HTTP export).
"""
import time
from loguru import logger
from data_processor import BiometricReading
from providers.base import BiometricProvider


class GadgetbridgeProvider(BiometricProvider):
    """Receives webhook POSTs from Gadgetbridge and converts to BiometricReading."""

    def __init__(self):
        self._latest: BiometricReading | None = None

    @property
    def name(self) -> str:
        return "gadgetbridge"

    async def start(self):
        logger.info("Gadgetbridge provider started (webhook mode)")

    async def stop(self):
        pass

    async def get_latest(self) -> BiometricReading | None:
        return self._latest

    def process_webhook(self, data: dict) -> BiometricReading:
        """Convert Gadgetbridge webhook payload to BiometricReading.

        Gadgetbridge may send data in various formats depending on the relay
        (Tasker, Automate, custom app). This normalizes common field names.
        """
        reading = BiometricReading(
            timestamp=time.time(),
            provider=self.name,
        )

        # Heart rate
        hr = data.get("heart_rate") or data.get("heartRate") or data.get("hr")
        if hr is not None:
            reading.heart_rate = int(hr)

        rhr = data.get("resting_heart_rate") or data.get("restingHeartRate")
        if rhr is not None:
            reading.resting_heart_rate = int(rhr)

        # SpO2
        spo2 = data.get("spo2") or data.get("oxygen_saturation") or data.get("blood_oxygen")
        if spo2 is not None:
            reading.spo2 = int(spo2)

        # Steps
        steps = data.get("steps") or data.get("step_count")
        if steps is not None:
            reading.steps = int(steps)

        steps_goal = data.get("steps_goal") or data.get("daily_goal")
        if steps_goal is not None:
            reading.steps_goal = int(steps_goal)

        # Calories
        cal = data.get("calories") or data.get("calories_burned")
        if cal is not None:
            reading.calories = int(cal)

        # Stress
        stress = data.get("stress") or data.get("stress_level")
        if stress is not None:
            reading.stress_level = int(stress)

        # Activity
        activity = data.get("activity_level") or data.get("activity")
        if activity is not None:
            reading.activity_level = str(activity)

        active_min = data.get("active_minutes")
        if active_min is not None:
            reading.active_minutes = int(active_min)

        # Sleep
        sleep_stage = data.get("sleep_stage") or data.get("sleep_state")
        if sleep_stage is not None:
            reading.sleep_stage = str(sleep_stage)

        sleep_dur = data.get("sleep_duration") or data.get("sleep_duration_minutes")
        if sleep_dur is not None:
            reading.sleep_duration_minutes = int(sleep_dur)

        sleep_deep = data.get("sleep_deep") or data.get("deep_sleep_minutes")
        if sleep_deep is not None:
            reading.sleep_deep_minutes = int(sleep_deep)

        sleep_rem = data.get("sleep_rem") or data.get("rem_sleep_minutes")
        if sleep_rem is not None:
            reading.sleep_rem_minutes = int(sleep_rem)

        sleep_light = data.get("sleep_light") or data.get("light_sleep_minutes")
        if sleep_light is not None:
            reading.sleep_light_minutes = int(sleep_light)

        sleep_quality = data.get("sleep_quality") or data.get("sleep_score")
        if sleep_quality is not None:
            reading.sleep_quality_score = int(sleep_quality)

        sleep_start = data.get("sleep_start_ts") or data.get("sleep_start")
        if sleep_start is not None:
            reading.sleep_start_ts = float(sleep_start)

        sleep_end = data.get("sleep_end_ts") or data.get("sleep_end")
        if sleep_end is not None:
            reading.sleep_end_ts = float(sleep_end)

        # HRV (Heart Rate Variability)
        hrv = data.get("hrv") or data.get("heart_rate_variability") or data.get("hrv_ms") or data.get("rmssd")
        if hrv is not None:
            reading.hrv_ms = int(hrv)

        # Body / skin temperature
        body_temp = (data.get("body_temperature") or data.get("body_temp")
                     or data.get("skin_temperature") or data.get("temperature"))
        if body_temp is not None:
            try:
                val = float(body_temp)
                if 30.0 <= val <= 45.0:  # sanity check for body temp range
                    reading.body_temperature = val
            except (ValueError, TypeError):
                pass

        # Respiratory rate
        resp = (data.get("respiratory_rate") or data.get("respiration_rate")
                or data.get("breathing_rate") or data.get("resp_rate"))
        if resp is not None:
            reading.respiratory_rate = int(resp)

        self._latest = reading
        logger.debug(f"Gadgetbridge webhook processed: hr={reading.heart_rate}, steps={reading.steps}")
        return reading
