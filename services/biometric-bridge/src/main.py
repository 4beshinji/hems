"""
HEMS Biometric Bridge — receives biometric data from Gadgetbridge (webhook)
and optionally Zepp Cloud API, normalizes it, and publishes to MQTT.
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from loguru import logger

from config import (
    MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, MQTT_TOPIC_PREFIX,
    BIOMETRIC_PROVIDER, ZEPP_ENABLED, ZEPP_EMAIL, ZEPP_PASSWORD, ZEPP_POLL_INTERVAL,
)
from mqtt_publisher import MQTTPublisher
from data_processor import DataProcessor, BiometricReading
from providers.gadgetbridge import GadgetbridgeProvider
from providers.zepp import ZeppProvider

# Module-level state
mqtt_pub: MQTTPublisher | None = None
processor = DataProcessor()
gadgetbridge = GadgetbridgeProvider()
zepp: ZeppProvider | None = None
_tasks: list[asyncio.Task] = []


def _publish_reading(reading: BiometricReading):
    """Publish individual metric topics from a reading."""
    if not mqtt_pub:
        return

    provider = reading.provider or BIOMETRIC_PROVIDER
    prefix = f"{MQTT_TOPIC_PREFIX}/{provider}"

    if reading.heart_rate is not None:
        data = {"bpm": reading.heart_rate}
        if reading.resting_heart_rate is not None:
            data["resting_bpm"] = reading.resting_heart_rate
        mqtt_pub.publish(f"{prefix}/heart_rate", data)

    if reading.spo2 is not None:
        mqtt_pub.publish(f"{prefix}/spo2", {"percent": reading.spo2})

    if reading.steps is not None:
        data = {"count": reading.steps}
        if reading.steps_goal is not None:
            data["daily_goal"] = reading.steps_goal
        mqtt_pub.publish(f"{prefix}/steps", data)

    if reading.stress_level is not None:
        from data_processor import BiometricReading as _BR
        category = "relaxed" if reading.stress_level < 25 else \
                   "normal" if reading.stress_level < 50 else \
                   "moderate" if reading.stress_level < 75 else "high"
        mqtt_pub.publish(f"{prefix}/stress", {
            "level": reading.stress_level, "category": category,
        })

    if reading.sleep_stage is not None or reading.sleep_duration_minutes is not None:
        sleep_data = {}
        if reading.sleep_stage is not None:
            sleep_data["stage"] = reading.sleep_stage
        if reading.sleep_duration_minutes is not None:
            sleep_data["duration_minutes"] = reading.sleep_duration_minutes
        if reading.sleep_deep_minutes is not None:
            sleep_data["deep_minutes"] = reading.sleep_deep_minutes
        if reading.sleep_rem_minutes is not None:
            sleep_data["rem_minutes"] = reading.sleep_rem_minutes
        if reading.sleep_light_minutes is not None:
            sleep_data["light_minutes"] = reading.sleep_light_minutes
        if reading.sleep_quality_score is not None:
            sleep_data["quality_score"] = reading.sleep_quality_score
        if reading.sleep_start_ts is not None:
            sleep_data["sleep_start_ts"] = reading.sleep_start_ts
        if reading.sleep_end_ts is not None:
            sleep_data["sleep_end_ts"] = reading.sleep_end_ts
        mqtt_pub.publish(f"{prefix}/sleep", sleep_data)
        processor.update_sleep_summary(reading)

    if reading.activity_level is not None or reading.calories is not None:
        activity_data = {}
        if reading.activity_level is not None:
            activity_data["level"] = reading.activity_level
        if reading.calories is not None:
            activity_data["calories"] = reading.calories
        if reading.active_minutes is not None:
            activity_data["active_minutes"] = reading.active_minutes
        if reading.steps is not None:
            activity_data["steps"] = reading.steps
        mqtt_pub.publish(f"{prefix}/activity", activity_data)

    if reading.hrv_ms is not None:
        mqtt_pub.publish(f"{prefix}/hrv", {"rmssd_ms": reading.hrv_ms})

    if reading.body_temperature is not None:
        mqtt_pub.publish(f"{prefix}/body_temperature", {"celsius": reading.body_temperature})

    if reading.respiratory_rate is not None:
        mqtt_pub.publish(f"{prefix}/respiratory_rate", {"breaths_per_minute": reading.respiratory_rate})

    # Compute and publish fatigue
    fatigue = processor.compute_fatigue()
    if fatigue["score"] > 0:
        mqtt_pub.publish(f"{prefix}/fatigue", fatigue)


async def _bridge_status_loop():
    """Periodically publish bridge status."""
    while True:
        if mqtt_pub:
            mqtt_pub.publish(f"{MQTT_TOPIC_PREFIX}/bridge/status", {
                "connected": True,
                "provider": BIOMETRIC_PROVIDER,
            })
        await asyncio.sleep(60)


async def _zepp_poll_loop():
    """Poll Zepp API periodically for batch data."""
    if not zepp:
        return
    while True:
        try:
            reading = await zepp.poll()
            if reading:
                processor.process(reading)
                _publish_reading(reading)
        except Exception as e:
            logger.error(f"Zepp poll error: {e}")
        await asyncio.sleep(ZEPP_POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_pub, zepp

    mqtt_pub = MQTTPublisher(MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS)
    try:
        mqtt_pub.connect()
    except Exception as e:
        logger.error(f"MQTT connect failed: {e}")
        mqtt_pub = None

    await gadgetbridge.start()

    if ZEPP_ENABLED:
        zepp = ZeppProvider(ZEPP_EMAIL, ZEPP_PASSWORD, ZEPP_POLL_INTERVAL)
        await zepp.start()
        _tasks.append(asyncio.create_task(_zepp_poll_loop()))

    _tasks.append(asyncio.create_task(_bridge_status_loop()))

    logger.info(f"Biometric Bridge started (provider={BIOMETRIC_PROVIDER})")
    yield

    for t in _tasks:
        t.cancel()
    if zepp:
        await zepp.stop()
    await gadgetbridge.stop()
    if mqtt_pub:
        mqtt_pub.disconnect()


app = FastAPI(title="HEMS Biometric Bridge", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "provider": BIOMETRIC_PROVIDER}


@app.post("/api/biometric/webhook")
async def receive_webhook(request: Request):
    """Receive biometric data from Gadgetbridge (or similar apps)."""
    data = await request.json()
    reading = gadgetbridge.process_webhook(data)
    processed = processor.process(reading)
    _publish_reading(processed)
    return {"received": True, "provider": gadgetbridge.name}


@app.get("/api/biometric/latest")
async def get_latest():
    """Get the latest biometric reading."""
    reading = processor.get_latest()
    if not reading:
        return {"status": "no_data"}
    result = {"provider": reading.provider, "timestamp": reading.timestamp}
    if reading.heart_rate is not None:
        result["heart_rate"] = reading.heart_rate
    if reading.spo2 is not None:
        result["spo2"] = reading.spo2
    if reading.steps is not None:
        result["steps"] = reading.steps
    if reading.stress_level is not None:
        result["stress_level"] = reading.stress_level
    if reading.activity_level is not None:
        result["activity_level"] = reading.activity_level
    if reading.hrv_ms is not None:
        result["hrv_ms"] = reading.hrv_ms
    if reading.body_temperature is not None:
        result["body_temperature"] = reading.body_temperature
    if reading.respiratory_rate is not None:
        result["respiratory_rate"] = reading.respiratory_rate
    fatigue = processor.compute_fatigue()
    result["fatigue"] = fatigue
    return result


@app.get("/api/biometric/sleep")
async def get_sleep():
    """Get last night's sleep summary."""
    summary = processor.get_sleep_summary()
    if not summary:
        return {"status": "no_data"}
    return summary


@app.get("/api/biometric/activity")
async def get_activity():
    """Get today's activity summary."""
    reading = processor.get_latest()
    if not reading:
        return {"status": "no_data"}
    result = {}
    if reading.steps is not None:
        result["steps"] = reading.steps
    if reading.steps_goal is not None:
        result["steps_goal"] = reading.steps_goal
    if reading.calories is not None:
        result["calories"] = reading.calories
    if reading.active_minutes is not None:
        result["active_minutes"] = reading.active_minutes
    if reading.activity_level is not None:
        result["activity_level"] = reading.activity_level
    return result if result else {"status": "no_data"}
