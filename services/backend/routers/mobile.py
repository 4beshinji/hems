"""
Mobile companion endpoints.

Device registration (``/mobile/register``) is accessible via the frontend
management page (QR flow).

All subsequent endpoints authenticate via the per-device key returned at
registration time, plus an HMAC-SHA256 signature on the raw request body
for the state webhook (the high-volume sensor path).
"""

import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
import schemas
from auth import (
    generate_device_credentials,
    verify_api_key,
    verify_mobile_device,
)
from database import get_db
from hmac_util import verify_signature

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_USER = os.getenv("MQTT_USER", "hems")
MQTT_PASS = os.getenv("MQTT_PASS", "hems_dev_mqtt")

# Character version string surfaced in the registration response so the phone
# can invalidate cached voice-capsule bundles when the persona changes.
CHARACTER_VERSION = os.getenv("CHARACTER_VERSION", os.getenv("CHARACTER", "default"))

# Phone-visible backend URL (defaults to LAN hostname form). Included in the
# registration response / QR payload so the app knows where to reach us.
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "")

# Voice-service base URL — backend proxies capsule audio downloads so the
# phone never needs direct voice-service reachability.
VOICE_SERVICE_URL = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")

# Only allow the capsule-naming convention to cross the proxy. Keeps the
# audio endpoint from doubling as a general voice-service proxy.
_AUDIO_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.(?:mp3|wav|ogg)$")

# Admin-only routes (register, list, revoke).
admin_router = APIRouter(
    prefix="/mobile",
    tags=["mobile-admin"],
    dependencies=[Depends(verify_api_key)],
)

# Device-authenticated routes (webhooks, capsule retrieval — capsule added later phase).
device_router = APIRouter(prefix="/mobile", tags=["mobile-device"])


def _publish_mobile_event(subtopic: str, payload: dict) -> list[str]:
    """Publish a mobile event to ``hems/personal/mobile/<subtopic>`` and return topics published.

    Mirrors the synchronous paho pattern used in :mod:`routers.shopping`.
    """
    topic = f"hems/personal/mobile/{subtopic}"
    body = json.dumps(payload, ensure_ascii=False, default=str)
    try:
        import paho.mqtt.publish as mqtt_publish

        mqtt_publish.single(
            topic,
            body,
            hostname=MQTT_BROKER,
            auth={"username": MQTT_USER, "password": MQTT_PASS},
        )
        return [topic]
    except Exception as exc:
        logger.warning("MQTT publish failed for mobile %s: %s", topic, exc)
        return []


# ---------------------------------------------------------------- admin ---


@admin_router.post("/register", response_model=schemas.MobileDeviceRegisterResponse)
async def register_device(
    body: schemas.MobileDeviceRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new mobile device entry and issue its credentials.

    The plaintext ``device_key`` is returned ONCE here — the caller (frontend
    admin page) is expected to render it as a QR code and immediately drop it.
    Only the hash is retained server-side.
    """
    device_key, api_key_hash, hmac_secret = generate_device_credentials()

    device = models.MobileDevice(
        device_label=body.device_label,
        api_key_hash=api_key_hash,
        hmac_secret=hmac_secret,
        platform=body.platform,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)

    return schemas.MobileDeviceRegisterResponse(
        device_id=device.id,
        device_key=device_key,
        hmac_secret=hmac_secret,
        backend_url=BACKEND_PUBLIC_URL or None,
        character_version=CHARACTER_VERSION,
    )


@admin_router.get("/devices", response_model=list[schemas.MobileDevice])
async def list_devices(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.MobileDevice).order_by(models.MobileDevice.registered_at.desc()))
    return result.scalars().all()


@admin_router.get(
    "/voice-capsule/play-log",
    response_model=list[schemas.VoiceCapsulePlayLogRecord],
)
async def list_play_logs(
    capsule_date: str | None = None,
    clip_id: str | None = None,
    since_days: int = 30,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    """List playback acks for ack-learning. Brain polls this periodically."""
    since = datetime.now(UTC) - timedelta(days=since_days)
    query = select(models.VoiceCapsulePlayLog).where(
        models.VoiceCapsulePlayLog.played_at >= since,
    )
    if capsule_date:
        sub = select(models.VoiceCapsule.id).where(
            models.VoiceCapsule.capsule_date == capsule_date,
        )
        query = query.where(models.VoiceCapsulePlayLog.capsule_id.in_(sub))
    if clip_id:
        query = query.where(models.VoiceCapsulePlayLog.clip_id == clip_id)
    query = query.order_by(models.VoiceCapsulePlayLog.played_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


@admin_router.post(
    "/voice-capsule",
    response_model=schemas.VoiceCapsuleManifest,
    status_code=201,
)
async def upsert_voice_capsule(
    body: schemas.VoiceCapsuleManifest,
    db: AsyncSession = Depends(get_db),
):
    """Write-or-replace a capsule keyed by ``capsule_id`` (which is the date).

    Brain calls this at boot-load time with the freshly built manifest. Prior
    capsules for the same date are overwritten in place — phones observe the
    change on their next ``/latest`` poll.
    """
    raw = body.model_dump_json(exclude_none=True)
    result = await db.execute(select(models.VoiceCapsule).where(models.VoiceCapsule.capsule_date == body.capsule_id))
    existing = result.scalars().first()
    if existing is not None:
        existing.manifest_json = raw
        existing.character_version = body.character_version or existing.character_version
        existing.expires_at = body.expires_at
        existing.invalidated = False
        existing.generated_at = datetime.now(UTC)
    else:
        existing = models.VoiceCapsule(
            capsule_date=body.capsule_id,
            character_version=body.character_version,
            manifest_json=raw,
            expires_at=body.expires_at,
        )
        db.add(existing)

    await db.commit()
    await db.refresh(existing)
    return await _capsule_to_manifest(existing)


@admin_router.delete("/devices/{device_id}")
async def disable_device(device_id: int, db: AsyncSession = Depends(get_db)):
    """Soft-disable a device. The key is left in place to preserve play-log FK integrity."""
    result = await db.execute(select(models.MobileDevice).where(models.MobileDevice.id == device_id))
    device = result.scalars().first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    device.enabled = False
    await db.commit()
    return {"disabled": True, "device_id": device_id}


# --------------------------------------------------------------- device ---


@device_router.post("/state/webhook", response_model=schemas.MobileStateWebhookResponse)
async def state_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    device: models.MobileDevice = Depends(verify_mobile_device),
):
    """Accept a batched sensor / biometric / location push from the phone.

    Body must be signed with the per-device ``hmac_secret`` using HMAC-SHA256
    and presented in the ``X-HEMS-Signature: sha256=<hex>`` header. The raw
    body is read *once* and parsed only after signature validation.
    """
    body = await request.body()
    sig_header = request.headers.get("X-HEMS-Signature", "")
    if not verify_signature(device.hmac_secret, body, sig_header):
        logger.warning("Mobile state webhook rejected: bad HMAC (device_id=%s)", device.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-HEMS-Signature",
        )

    try:
        payload = schemas.MobileStateWebhookPayload.model_validate_json(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Malformed payload: {exc}") from exc

    ts_iso = payload.ts.astimezone(UTC).isoformat()
    published: list[str] = []

    if payload.location is not None:
        published += _publish_mobile_event(
            "location",
            {
                **payload.location.model_dump(exclude_none=True),
                "ts": ts_iso,
                "device_id": device.id,
            },
        )

    if payload.activity is not None:
        published += _publish_mobile_event(
            "activity",
            {
                **payload.activity.model_dump(exclude_none=True),
                "ts": ts_iso,
                "device_id": device.id,
            },
        )

    if payload.biometrics is not None:
        published += _publish_mobile_event(
            "biometrics",
            {
                **payload.biometrics.model_dump(exclude_none=True),
                "ts": ts_iso,
                "device_id": device.id,
            },
        )

    if payload.battery_pct is not None:
        published += _publish_mobile_event(
            "battery",
            {
                "percent": payload.battery_pct,
                "ts": ts_iso,
                "device_id": device.id,
            },
        )

    device.last_seen_at = datetime.now(UTC)
    await db.commit()

    return schemas.MobileStateWebhookResponse(received=True, published_topics=published)


# ------------------------------------------------------------- voice-capsule ---


async def _capsule_to_manifest(capsule: models.VoiceCapsule) -> schemas.VoiceCapsuleManifest:
    raw = json.loads(capsule.manifest_json)
    return schemas.VoiceCapsuleManifest.model_validate(raw)


@device_router.get(
    "/voice-capsule/latest",
    response_model=schemas.VoiceCapsuleManifest,
)
async def get_latest_capsule(
    db: AsyncSession = Depends(get_db),
    device: models.MobileDevice = Depends(verify_mobile_device),
):
    """Return the newest non-invalidated capsule manifest."""
    result = await db.execute(
        select(models.VoiceCapsule)
        .where(models.VoiceCapsule.invalidated == False)
        .order_by(
            models.VoiceCapsule.generated_at.desc(),
            models.VoiceCapsule.id.desc(),  # tie-breaker when inserts share a second
        )
        .limit(1)
    )
    capsule = result.scalars().first()
    if capsule is None:
        raise HTTPException(status_code=404, detail="No capsule available")
    return await _capsule_to_manifest(capsule)


@device_router.get(
    "/voice-capsule/{capsule_id}",
    response_model=schemas.VoiceCapsuleManifest,
)
async def get_capsule(
    capsule_id: str,
    db: AsyncSession = Depends(get_db),
    device: models.MobileDevice = Depends(verify_mobile_device),
):
    """Return a specific capsule by its logical id (``capsule_date``)."""
    result = await db.execute(select(models.VoiceCapsule).where(models.VoiceCapsule.capsule_date == capsule_id))
    capsule = result.scalars().first()
    if capsule is None:
        raise HTTPException(status_code=404, detail="Capsule not found")
    return await _capsule_to_manifest(capsule)


@device_router.post("/voice-capsule/ack", status_code=204)
async def ack_capsule_play(
    body: schemas.VoiceCapsulePlayAck,
    db: AsyncSession = Depends(get_db),
    device: models.MobileDevice = Depends(verify_mobile_device),
):
    """Log one clip playback event from the phone for ack-learning."""
    result = await db.execute(select(models.VoiceCapsule).where(models.VoiceCapsule.capsule_date == body.capsule_id))
    capsule = result.scalars().first()
    if capsule is None:
        raise HTTPException(status_code=404, detail="Capsule not found")

    log = models.VoiceCapsulePlayLog(
        capsule_id=capsule.id,
        clip_id=body.clip_id,
        played_at=body.played_at,
        trigger_drift_sec=body.trigger_drift_sec,
        context_json=body.context_json,
    )
    db.add(log)
    await db.commit()


@device_router.get("/voice-capsule/audio/{filename}")
async def stream_capsule_audio(
    filename: str,
    device: models.MobileDevice = Depends(verify_mobile_device),
):
    """Proxy audio download from voice-service, gated by device auth.

    Uses an httpx streaming response so large files don't land in memory.
    The filename must match :data:`_AUDIO_FILENAME_RE` to prevent using this
    route as a general proxy into the voice-service namespace.
    """
    if not _AUDIO_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    import httpx  # local import — backend already ships with httpx for chat TTS

    upstream = f"{VOICE_SERVICE_URL}/audio/{filename}"

    async def _stream():
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            async with client.stream("GET", upstream) as resp:
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail="Audio unavailable")
                async for chunk in resp.aiter_bytes():
                    yield chunk

    media_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
    return StreamingResponse(_stream(), media_type=media_type)
