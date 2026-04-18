"""
Sunrise Alarm — gradual brightness ramp before predicted wake time.

Ramps a Zigbee light from minimum to maximum brightness over a configurable
window before the predicted wake time, simulating sunrise. On wake_up event
detection, the light is turned off.

State machine:
  IDLE    — waiting; not yet in the ramp window
  RAMPING — async task is stepping brightness up
  DONE    — ramp completed, at max brightness; waiting for wake_up to turn off

Triggered by cognitive_cycle() when:
  - PowerModeManager is in SLEEP mode
  - schedule_learner.get_wake_time() returns a timestamp within START_BEFORE_SEC
"""

import asyncio
import json
import os
import time
from datetime import datetime
from enum import StrEnum

from loguru import logger

# Config via env vars
DEVICE_ID = os.getenv("SUNRISE_ALARM_DEVICE", "")  # e.g. "zigbee.0x781c9dfffee1557e"
START_BEFORE_SEC = int(os.getenv("SUNRISE_ALARM_START_SEC", "7200"))  # 2h before wake
END_BEFORE_SEC = int(os.getenv("SUNRISE_ALARM_END_SEC", "1800"))  # 30min before wake
MIN_BRIGHTNESS = int(os.getenv("SUNRISE_ALARM_MIN_BRIGHTNESS", "1"))
MAX_BRIGHTNESS = int(os.getenv("SUNRISE_ALARM_MAX_BRIGHTNESS", "254"))
STEP_SEC = int(os.getenv("SUNRISE_ALARM_STEP_SEC", "30"))


class SunriseState(StrEnum):
    IDLE = "idle"
    RAMPING = "ramping"
    DONE = "done"


class SunriseAlarm:
    """Gradual brightness ramp synced to predicted wake time."""

    def __init__(self):
        self._state = SunriseState.IDLE
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mqtt_client = None
        self._last_run_date: str | None = None
        # Strip vendor prefix → zigbee2mqtt friendly_name / IEEE address
        self._device_ref: str = DEVICE_ID.removeprefix("zigbee.") if DEVICE_ID else ""

    @property
    def state(self) -> SunriseState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state in (SunriseState.RAMPING, SunriseState.DONE)

    def should_start(self, schedule_learner, now: float | None = None) -> bool:
        """Return True if ramp should begin (within START_BEFORE_SEC of wake)."""
        if not DEVICE_ID or self._state != SunriseState.IDLE:
            return False
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_run_date == today:
            return False
        if schedule_learner is None:
            return False
        wake_ts = schedule_learner.get_wake_time()
        if wake_ts is None:
            return False
        remaining = wake_ts - (now or time.time())
        return 0 < remaining < START_BEFORE_SEC

    def start(self, mqtt_client, wake_ts: float) -> asyncio.Task:
        """Launch brightness ramp as a background asyncio.Task."""
        self._state = SunriseState.RAMPING
        self._last_run_date = datetime.now().strftime("%Y-%m-%d")
        self._mqtt_client = mqtt_client
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._ramp(mqtt_client, wake_ts))
        return self._task

    def stop(self, mqtt_client=None):
        """Cancel ramp and turn off the light. Thread-safe (called from MQTT thread)."""
        if self._task and not self._task.done():
            if self._loop:
                self._loop.call_soon_threadsafe(self._task.cancel)

        client = mqtt_client or self._mqtt_client
        if client and self._device_ref:
            topic = f"zigbee2mqtt/{self._device_ref}/set"
            client.publish(topic, json.dumps({"state": "OFF"}))
            logger.info("[SunriseAlarm] 起床検知 → 消灯")

        self._state = SunriseState.IDLE

    async def _ramp(self, mqtt_client, wake_ts: float):
        """Gradually increase brightness from MIN to MAX."""
        try:
            ramp_start = wake_ts - START_BEFORE_SEC
            ramp_end = wake_ts - END_BEFORE_SEC
            ramp_duration = ramp_end - ramp_start
            topic = f"zigbee2mqtt/{self._device_ref}/set"

            # Wait until ramp start if checked slightly early
            now = time.time()
            if now < ramp_start:
                await asyncio.sleep(ramp_start - now)

            # Turn on at minimum brightness
            mqtt_client.publish(topic, json.dumps({
                "state": "ON",
                "brightness": MIN_BRIGHTNESS,
            }))
            logger.info(
                "[SunriseAlarm] ランプ開始: %s brightness %d→%d (%dmin)",
                self._device_ref, MIN_BRIGHTNESS, MAX_BRIGHTNESS,
                int(ramp_duration / 60),
            )

            last_brightness = MIN_BRIGHTNESS
            while True:
                await asyncio.sleep(STEP_SEC)
                elapsed = time.time() - ramp_start
                progress = min(elapsed / ramp_duration, 1.0)
                brightness = int(
                    MIN_BRIGHTNESS + (MAX_BRIGHTNESS - MIN_BRIGHTNESS) * progress
                )
                brightness = max(MIN_BRIGHTNESS, min(MAX_BRIGHTNESS, brightness))

                if brightness != last_brightness:
                    mqtt_client.publish(topic, json.dumps({"brightness": brightness}))
                    last_brightness = brightness

                if progress >= 1.0:
                    break

            self._state = SunriseState.DONE
            logger.info("[SunriseAlarm] ランプ完了 → brightness %d", MAX_BRIGHTNESS)

        except asyncio.CancelledError:
            logger.info("[SunriseAlarm] キャンセル")
            self._state = SunriseState.IDLE
            raise
        except Exception as e:
            logger.error("[SunriseAlarm] エラー: %s", e)
            self._state = SunriseState.IDLE
