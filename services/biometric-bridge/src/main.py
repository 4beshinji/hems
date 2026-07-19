"""
HEMS Biometric Bridge — dual-path biometric data ingestion.

Path 1: Webhook (Health Connect Companion App or Gadgetbridge)
Path 2: Huami cloud API polling (Xiaomi Smart Band / Amazfit via Mi Fitness)

Deduplication prevents duplicate MQTT publishes when both paths deliver
the same data within the configured window.
"""

import asyncio
import hashlib
import hmac
import json as _json
import os
import time
from collections import OrderedDict
from contextlib import asynccontextmanager

from canonical_ingest import CanonicalObservationStore, ObservationConflictError, ObservationStoreError
from data_processor import BiometricReading, DataProcessor
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from loguru import logger
from providers.gadgetbridge import GadgetbridgeProvider
from providers.huami import HuamiProvider
from providers.zepp import ZeppProvider
from send_queue import SendQueue

from config import (
    BIOMETRIC_PROVIDER,
    HUAMI_AUTH_TOKEN,
    HUAMI_ENABLED,
    HUAMI_POLL_INTERVAL,
    HUAMI_SERVER_REGION,
    HUAMI_USER_ID,
    MQTT_BROKER,
    MQTT_PASS,
    MQTT_PORT,
    MQTT_TOPIC_PREFIX,
    MQTT_USER,
    ZEPP_EMAIL,
    ZEPP_ENABLED,
    ZEPP_PASSWORD,
    ZEPP_POLL_INTERVAL,
)
from hems_common import (
    BiometricObservationIn,
    MqttPublisher,
    bridge_lifespan,
    publish_bridge_status,
    verify_internal_token,
)

# HMAC secret for webhook authentication.
# Set BIOMETRIC_WEBHOOK_SECRET in environment (required).
# Companion app must include header: X-HEMS-Signature: sha256=<hmac_hex>
_WEBHOOK_SECRET = os.getenv("BIOMETRIC_WEBHOOK_SECRET", "").encode()
_WEBHOOK_AUTH_ENABLED = bool(_WEBHOOK_SECRET)

# Replay protection (W1.3).
# When true, X-Timestamp and X-Nonce headers are required.
# While false, requests that omit them are accepted with a WARNING for backward
# compatibility with Gadgetbridge / Android companion apps that cannot be updated
# immediately.  Set WEBHOOK_REPLAY_STRICT=true once companion apps are updated.
_REPLAY_STRICT: bool = os.getenv("WEBHOOK_REPLAY_STRICT", "false").lower() in ("1", "true", "yes")

# Replay-protection constants (mirror hmac_util.py values; kept local to avoid
# a cross-service import dependency in the bridge container).
_REPLAY_WINDOW_SECONDS: int = 300  # ±5 minutes
_NONCE_CACHE_MAX: int = 10_000

# In-memory nonce cache.  Cleared on process restart — this is intentional and
# safe because the timestamp window prevents replay of old requests even with a
# cold cache.
_seen_nonces: OrderedDict[str, float] = OrderedDict()

if not _WEBHOOK_AUTH_ENABLED:
    logger.warning(
        "BIOMETRIC_WEBHOOK_SECRET is not set — webhook authentication DISABLED. "
        "Set this variable in production to prevent unauthorized data injection."
    )


def _check_nonce(nonce: str, now: float) -> bool:
    """Return True and record the nonce if unseen; False if already seen."""
    # Evict expired entries.
    cutoff = now - _REPLAY_WINDOW_SECONDS
    while _seen_nonces:
        _key, ts = next(iter(_seen_nonces.items()))
        if ts < cutoff:
            _seen_nonces.popitem(last=False)
        else:
            break
    while len(_seen_nonces) >= _NONCE_CACHE_MAX:
        _seen_nonces.popitem(last=False)

    if nonce in _seen_nonces:
        return False
    _seen_nonces[nonce] = now
    return True


async def _verify_webhook_signature(request: Request) -> bytes:
    """Read request body and verify HMAC-SHA256 signature with replay protection.

    New protocol (when X-Timestamp and X-Nonce are present):
        Sign message = ``<timestamp>:<nonce>:`` + raw body
        Header: X-HEMS-Signature: sha256=<hex>
        Header: X-Timestamp: <unix_seconds>
        Header: X-Nonce: <unique_opaque_string>

    Legacy protocol (X-Timestamp / X-Nonce absent):
        Sign message = raw body only
        Accepted only when WEBHOOK_REPLAY_STRICT=false (with a WARNING).

    Raises HTTPException(401) on any auth failure.
    Returns raw body bytes.
    """
    body = await request.body()

    if not _WEBHOOK_AUTH_ENABLED:
        return body

    sig_header = request.headers.get("X-HEMS-Signature", "")
    ts_header: str | None = request.headers.get("X-Timestamp") or None
    nonce_header: str | None = request.headers.get("X-Nonce") or None

    # --- Basic signature header check ---
    if not sig_header.startswith("sha256="):
        logger.warning("Biometric webhook rejected: missing X-HEMS-Signature header")
        raise HTTPException(
            status_code=401,
            detail="Missing X-HEMS-Signature header. Include: X-HEMS-Signature: sha256=<hmac-sha256-hex>",
        )

    provided_sig = sig_header[7:]

    # --- Replay protection ---
    now = time.time()

    if ts_header is None or nonce_header is None:
        # Headers absent — legacy path.
        if _REPLAY_STRICT:
            logger.warning("Biometric webhook rejected: X-Timestamp/X-Nonce required (WEBHOOK_REPLAY_STRICT=true)")
            raise HTTPException(
                status_code=401,
                detail="X-Timestamp and X-Nonce headers are required (WEBHOOK_REPLAY_STRICT=true)",
            )
        # Non-strict: fall through to legacy HMAC check and emit warning.
        signing_body = body
        _legacy = True
    else:
        _legacy = False
        # Validate timestamp.
        try:
            req_ts = float(ts_header)
        except (ValueError, TypeError):
            logger.warning("Biometric webhook rejected: X-Timestamp not numeric")
            raise HTTPException(status_code=401, detail="X-Timestamp must be a unix epoch integer")

        age = abs(now - req_ts)
        if age > _REPLAY_WINDOW_SECONDS:
            logger.warning(
                "Biometric webhook rejected: timestamp age=%.0fs (window=%ds)",
                age,
                _REPLAY_WINDOW_SECONDS,
            )
            raise HTTPException(
                status_code=401,
                detail=f"X-Timestamp outside ±{_REPLAY_WINDOW_SECONDS}s window",
            )

        # Validate nonce uniqueness.
        nonce = str(nonce_header).strip()
        if not nonce:
            raise HTTPException(status_code=401, detail="X-Nonce must not be empty")
        if not _check_nonce(nonce, now):
            logger.warning("Biometric webhook rejected: nonce reuse (replay detected)")
            raise HTTPException(status_code=401, detail="X-Nonce already used (replay detected)")

        # New signing message folds in timestamp + nonce.
        signing_body = f"{ts_header}:{nonce_header}:".encode() + body

    # --- HMAC check ---
    expected_sig = hmac.new(_WEBHOOK_SECRET, signing_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        logger.warning("Biometric webhook rejected: invalid HMAC signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if _legacy:
        logger.warning(
            "Biometric webhook accepted via legacy HMAC (no X-Timestamp/X-Nonce). "
            "Update Gadgetbridge / companion app to add replay-prevention headers. "
            "Set WEBHOOK_REPLAY_STRICT=true to enforce the new protocol."
        )

    return body


# Module-level state
mqtt_pub: MqttPublisher | None = None
send_queue: SendQueue = SendQueue()
canonical_store: CanonicalObservationStore = CanonicalObservationStore()
processor = DataProcessor()
gadgetbridge = GadgetbridgeProvider()
huami: HuamiProvider | None = None
zepp: ZeppProvider | None = None

# Routers: /health stays public for Docker healthchecks; /api/biometric/webhook stays
# public because external companion apps push to it. All other REST routes require the
# internal bearer token when HEMS_INTERNAL_TOKEN is configured.
public_router = APIRouter()
private_router = APIRouter(dependencies=[Depends(verify_internal_token)])


def _mqtt_publish(topic: str, data: dict, retain: bool = True):
    """Publish to MQTT; enqueue to SQLite if broker is unreachable."""
    if mqtt_pub and mqtt_pub.publish(topic, data, retain=retain):
        return
    # MQTT unavailable — queue for later
    asyncio.get_event_loop().create_task(send_queue.enqueue(topic, data, retain))


def _publish_reading(reading: BiometricReading):
    """Publish individual metric topics from a reading, with deduplication."""
    # Dual-path dedup: skip if same data was recently published
    if processor.is_duplicate(reading):
        return

    provider = reading.provider or BIOMETRIC_PROVIDER
    prefix = f"{MQTT_TOPIC_PREFIX}/{provider}"

    if reading.heart_rate is not None:
        data = {"bpm": reading.heart_rate}
        if reading.resting_heart_rate is not None:
            data["resting_bpm"] = reading.resting_heart_rate
        _mqtt_publish(f"{prefix}/heart_rate", data)

    if reading.spo2 is not None:
        _mqtt_publish(f"{prefix}/spo2", {"percent": reading.spo2})

    if reading.steps is not None:
        data = {"count": reading.steps}
        if reading.steps_goal is not None:
            data["daily_goal"] = reading.steps_goal
        _mqtt_publish(f"{prefix}/steps", data)

    if reading.stress_level is not None:
        category = (
            "relaxed"
            if reading.stress_level < 25
            else "normal"
            if reading.stress_level < 50
            else "moderate"
            if reading.stress_level < 75
            else "high"
        )
        _mqtt_publish(
            f"{prefix}/stress",
            {
                "level": reading.stress_level,
                "category": category,
            },
        )

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
        _mqtt_publish(f"{prefix}/sleep", sleep_data)
        processor.update_sleep_summary(reading)

    if reading.activity_level is not None or reading.calories is not None or reading.active_minutes is not None:
        activity_data = {}
        if reading.activity_level is not None:
            activity_data["level"] = reading.activity_level
        if reading.calories is not None:
            activity_data["calories"] = reading.calories
        if reading.active_minutes is not None:
            activity_data["active_minutes"] = reading.active_minutes
        # NOTE: steps is published only on /steps to avoid double publishing.
        # world_model already merges /steps and /activity into the same ActivityData.
        if activity_data:
            _mqtt_publish(f"{prefix}/activity", activity_data)

    if reading.hrv_ms is not None:
        _mqtt_publish(f"{prefix}/hrv", {"rmssd_ms": reading.hrv_ms})

    if reading.body_temperature is not None:
        _mqtt_publish(f"{prefix}/body_temperature", {"celsius": reading.body_temperature})

    if reading.respiratory_rate is not None:
        _mqtt_publish(f"{prefix}/respiratory_rate", {"breaths_per_minute": reading.respiratory_rate})

    # Compute and publish fatigue
    fatigue = processor.compute_fatigue()
    if fatigue["score"] > 0:
        _mqtt_publish(f"{prefix}/fatigue", fatigue)

    # Record published metrics for dedup
    processor.record_published(reading)


async def _bridge_status_loop():
    """Periodically publish bridge status (canonical: hems/biometric/bridge/status)."""
    while True:
        providers = [BIOMETRIC_PROVIDER]
        if huami and huami._running:
            providers.append("huami")
        if mqtt_pub:
            publish_bridge_status(
                mqtt_pub,
                "biometric",
                connected=True,
                provider=BIOMETRIC_PROVIDER,
                active_providers=providers,
            )
        await asyncio.sleep(60)


async def _flush_queue_loop():
    """Periodically flush queued MQTT messages when broker reconnects."""
    while True:
        try:
            if mqtt_pub and mqtt_pub.connected:
                flushed = await send_queue.flush(mqtt_pub)
                if flushed > 0:
                    remaining = await send_queue.pending_count()
                    if remaining > 0:
                        logger.info(f"Queue: {remaining} messages still pending")
        except Exception as e:
            logger.error(f"Queue flush error: {e}")
        await asyncio.sleep(10)


async def _huami_poll_loop():
    """Poll Huami API periodically for batch data."""
    if not huami:
        return
    while True:
        try:
            reading = await huami.poll()
            if reading:
                processor.process(reading)
                _publish_reading(reading)
        except Exception as e:
            logger.error(f"Huami poll error: {e}")
        await asyncio.sleep(HUAMI_POLL_INTERVAL)


async def _zepp_poll_loop():
    """Poll Zepp API periodically for batch data (legacy)."""
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
    global mqtt_pub, huami, zepp

    # biometric: connection tracking + auto-reconnect enable the send-queue contract
    # (connected property + publish() -> bool).  ensure_ascii=False preserves
    # existing UTF-8 payload bytes.  raise_on_connect_error=False matches the
    # original try/except so messages are queued rather than hard-failing.
    mqtt_pub = MqttPublisher(
        MQTT_BROKER,
        MQTT_PORT,
        MQTT_USER,
        MQTT_PASS,
        ensure_ascii=False,
        track_connection=True,
        auto_reconnect=True,
        raise_on_connect_error=False,
    )

    async def _startup():
        global huami, zepp
        await send_queue.init()
        await canonical_store.init()
        await gadgetbridge.start()

        # Huami cloud API (primary server-side path)
        if HUAMI_ENABLED:
            huami = HuamiProvider(
                HUAMI_AUTH_TOKEN,
                HUAMI_USER_ID,
                HUAMI_SERVER_REGION,
                HUAMI_POLL_INTERVAL,
            )
            await huami.start()

        # Zepp (legacy, kept for backward compat)
        if ZEPP_ENABLED and not HUAMI_ENABLED:
            zepp = ZeppProvider(ZEPP_EMAIL, ZEPP_PASSWORD, ZEPP_POLL_INTERVAL)
            await zepp.start()

        logger.info(f"Biometric Bridge started (provider={BIOMETRIC_PROVIDER}, huami={HUAMI_ENABLED})")

    async def _shutdown():
        if huami:
            await huami.stop()
        if zepp:
            await zepp.stop()
        await gadgetbridge.stop()
        await canonical_store.close()
        await send_queue.close()

    # Conditional poll loops — always include _bridge_status_loop and
    # _flush_queue_loop; huami/zepp loops are included when their provider is
    # enabled (the loops guard on their own global being set, so this is safe).
    task_factories = [_bridge_status_loop, _flush_queue_loop]
    if HUAMI_ENABLED:
        task_factories.append(_huami_poll_loop)
    if ZEPP_ENABLED and not HUAMI_ENABLED:
        task_factories.append(_zepp_poll_loop)

    async with bridge_lifespan(
        app,
        mqtt=mqtt_pub,
        on_startup=_startup,
        task_factories=task_factories,
        on_shutdown=_shutdown,
    ):
        yield


app = FastAPI(title="HEMS Biometric Bridge", lifespan=lifespan)


@public_router.get("/health")
async def health():
    providers = [BIOMETRIC_PROVIDER]
    if huami and huami._running:
        providers.append("huami")
    pending = await send_queue.pending_count()
    mqtt_connected = mqtt_pub.connected if mqtt_pub else False
    return {
        "status": "ok",
        "provider": BIOMETRIC_PROVIDER,
        "active_providers": providers,
        "mqtt_connected": mqtt_connected,
        "queue_pending": pending,
    }


@public_router.post("/api/biometric/webhook")
async def receive_webhook(request: Request):
    """Receive biometric data from Health Connect Companion App or Gadgetbridge.

    Requires HMAC-SHA256 signature when BIOMETRIC_WEBHOOK_SECRET is set.
    Include header: X-HEMS-Signature: sha256=<hmac_sha256_hex_of_body>

    The payload may include a "provider" field to identify the data source
    (e.g., "healthconnect", "gadgetbridge"). Defaults to configured provider.
    """
    body = await _verify_webhook_signature(request)
    try:
        data = _json.loads(body)
    except _json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    reading = gadgetbridge.process_webhook(data)

    # Override provider if specified in payload
    provider_name = data.get("provider")
    if provider_name:
        reading.provider = provider_name

    processed = processor.process(reading)
    _publish_reading(processed)
    return {"received": True, "provider": reading.provider}


@private_router.post("/api/biometric/ingest")
async def receive_canonical_observation(data: BiometricObservationIn):
    """Durably accept a canonical observation and its delivery intents."""
    try:
        duplicate = await canonical_store.ingest(data)
    except ObservationConflictError:
        raise HTTPException(status_code=409, detail="observation_id already exists with different payload") from None
    except ObservationStoreError:
        logger.exception("Canonical biometric ingest storage failure")
        raise HTTPException(status_code=503, detail="canonical biometric store unavailable") from None
    return {"accepted": True, "duplicate": duplicate, "observation_id": data.observation_id}


@private_router.get("/api/biometric/latest")
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


@private_router.get("/api/biometric/sleep")
async def get_sleep():
    """Get last night's sleep summary."""
    summary = processor.get_sleep_summary()
    if not summary:
        return {"status": "no_data"}
    return summary


@private_router.get("/api/biometric/activity")
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


app.include_router(public_router)
app.include_router(private_router)
