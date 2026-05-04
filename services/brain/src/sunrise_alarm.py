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

Output path:
  Prefer DeviceDispatcher (vendor-agnostic, capability-validated, registry-tracked).
  Fall back to direct zigbee2mqtt MQTT publish when the dispatcher is absent or
  the device hasn't been auto-registered yet. Direct publishes check paho's
  return code and retry once on failure so silent Z2M outages are at least
  surfaced in the logs.
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
        self._dispatcher = None
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

    def start(self, mqtt_client, wake_ts: float, dispatcher=None) -> asyncio.Task:
        """Launch brightness ramp as a background asyncio.Task.

        ``dispatcher`` (DeviceDispatcher) is preferred for publishes; if None
        or if a dispatched call fails, the ramp falls back to direct MQTT
        publish via ``mqtt_client``.
        """
        self._state = SunriseState.RAMPING
        self._last_run_date = datetime.now().strftime("%Y-%m-%d")
        self._mqtt_client = mqtt_client
        self._dispatcher = dispatcher
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._ramp(wake_ts))
        return self._task

    def stop(self, mqtt_client=None):
        """Cancel ramp and turn off the light. Thread-safe (called from MQTT thread)."""
        if self._task and not self._task.done():
            if self._loop:
                self._loop.call_soon_threadsafe(self._task.cancel)

        client = mqtt_client or self._mqtt_client
        if client and self._device_ref:
            self._direct_publish(client, {"state": "OFF"})
            logger.info("[SunriseAlarm] 起床検知 → 消灯")

        self._state = SunriseState.IDLE

    # ------------------------------------------------------------------ #
    #  Output adapters                                                     #
    # ------------------------------------------------------------------ #

    def _direct_publish(self, mqtt_client, payload: dict) -> bool:
        """Publish to zigbee2mqtt directly; check rc and retry once on failure.

        Returns True if the broker accepted the publish (rc == 0)."""
        topic = f"zigbee2mqtt/{self._device_ref}/set"
        body = json.dumps(payload)
        for attempt in (1, 2):
            try:
                info = mqtt_client.publish(topic, body)
                rc = getattr(info, "rc", 0)
                if rc == 0:
                    return True
                logger.warning(
                    "[SunriseAlarm] MQTT publish rc={} (attempt {}) topic={}",
                    rc,
                    attempt,
                    topic,
                )
            except Exception as e:
                logger.warning(
                    "[SunriseAlarm] MQTT publish exception (attempt {}): {}", attempt, e
                )
            if attempt == 1:
                time.sleep(1.0)
        logger.error("[SunriseAlarm] publish failed after retry: {}", topic)
        return False

    async def _async_publish(self, payload_action: str, params: dict | None = None) -> bool:
        """Send via DeviceDispatcher when available, else direct publish.

        ``payload_action`` is one of the device_dispatcher action names
        (``on``/``off``/``set_brightness``)."""
        if self._dispatcher is not None and DEVICE_ID:
            try:
                result = await self._dispatcher.dispatch(DEVICE_ID, payload_action, params or {})
                if result.get("success"):
                    return True
                logger.warning(
                    "[SunriseAlarm] dispatcher {} failed ({}) → fallback direct publish",
                    payload_action,
                    result.get("error"),
                )
            except Exception as e:
                logger.warning(
                    "[SunriseAlarm] dispatcher {} exception → fallback direct publish: {}",
                    payload_action,
                    e,
                )

        if self._mqtt_client is None:
            logger.error("[SunriseAlarm] no mqtt_client available for fallback publish")
            return False
        # Build the same Z2M payload the dispatcher would have sent
        if payload_action == "on":
            body = {"state": "ON"}
        elif payload_action == "off":
            body = {"state": "OFF"}
        elif payload_action == "set_brightness":
            body = {"state": "ON", "brightness": int((params or {}).get("value", MIN_BRIGHTNESS))}
        else:
            logger.error("[SunriseAlarm] unknown payload_action {}", payload_action)
            return False
        return await asyncio.get_running_loop().run_in_executor(
            None, self._direct_publish, self._mqtt_client, body
        )

    async def _ramp(self, wake_ts: float):
        """Gradually increase brightness from MIN to MAX."""
        try:
            ramp_start = wake_ts - START_BEFORE_SEC
            ramp_end = wake_ts - END_BEFORE_SEC
            ramp_duration = ramp_end - ramp_start

            # Wait until ramp start if checked slightly early
            now = time.time()
            if now < ramp_start:
                await asyncio.sleep(ramp_start - now)

            # Turn on at minimum brightness
            await self._async_publish("set_brightness", {"value": MIN_BRIGHTNESS})
            logger.info(
                "[SunriseAlarm] ランプ開始: {} brightness {}→{} ({}min)",
                self._device_ref,
                MIN_BRIGHTNESS,
                MAX_BRIGHTNESS,
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
                    await self._async_publish("set_brightness", {"value": brightness})
                    last_brightness = brightness

                if progress >= 1.0:
                    break

            self._state = SunriseState.DONE
            logger.info("[SunriseAlarm] ランプ完了 → brightness {}", MAX_BRIGHTNESS)

        except asyncio.CancelledError:
            logger.info("[SunriseAlarm] キャンセル")
            self._state = SunriseState.IDLE
            raise
        except Exception as e:
            logger.error("[SunriseAlarm] エラー: {}", e)
            self._state = SunriseState.IDLE
