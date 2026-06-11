"""
Device Registry — unified sensor + actuator CRUD.

Brain pushes heartbeats on MQTT-observed devices (auto-register).
Frontend performs CRUD on metadata (display_name / purpose / zone / ...).
Control requests are proxied to Brain which dispatches to the vendor bridge.
"""

import logging
import os
import re
from datetime import UTC, datetime

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
import schemas
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])

BRAIN_URL = os.getenv("BRAIN_CHAT_URL", "http://brain:8080")

_IEEE_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{16}$")


def _brain_auth_headers() -> dict:
    """Authorization header for backend → brain chat-server proxied requests.

    Carries ``HEMS_INTERNAL_TOKEN`` as a Bearer token when set; returns ``{}``
    (no header) in zero-config / dev deployments. Reads env each call so a
    live-reloaded token takes effect without restarting the backend.
    """
    token = os.getenv("HEMS_INTERNAL_TOKEN", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _is_placeholder_name(name: str | None, device_id: str | None = None) -> bool:
    """A display_name is 'placeholder' if it's empty, a raw Zigbee IEEE address,
    or identical to the device_id — i.e. nothing the user would have typed."""
    if not name:
        return True
    if _IEEE_ADDR_RE.match(name):
        return True
    if device_id and name == device_id:
        return True
    return False


def _apply_update(device: models.Device, updates: dict) -> None:
    for field, value in updates.items():
        if value is not None or field in (
            "notes",
            "purpose",
            "location",
            "description",
            "display_name",
            "metadata_json",
        ):
            setattr(device, field, value)


@router.get("/", response_model=list[schemas.Device])
async def list_devices(
    kind: str | None = Query(None, description="sensor|actuator|both"),
    vendor: str | None = Query(None),
    zone: str | None = Query(None),
    device_class: str | None = Query(None),
    capability: str | None = Query(None),
    enabled_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    query = select(models.Device)
    if kind:
        query = query.filter(models.Device.kind == kind)
    if vendor:
        query = query.filter(models.Device.vendor == vendor)
    if zone:
        query = query.filter(models.Device.zone == zone)
    if device_class:
        query = query.filter(models.Device.device_class == device_class)
    if enabled_only:
        query = query.filter(models.Device.is_enabled == True)
    query = query.order_by(models.Device.zone, models.Device.device_id)
    result = await db.execute(query)
    devices = result.scalars().all()
    if capability:
        devices = [d for d in devices if capability in (d.capabilities or [])]
    return devices


@router.get("/{device_id}", response_model=schemas.Device)
async def get_device(device_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Device).filter(models.Device.device_id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return device


@router.post("/", response_model=schemas.Device)
async def create_device(body: schemas.DeviceCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(models.Device).filter(models.Device.device_id == body.device_id))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail=f"Device '{body.device_id}' already exists")

    device = models.Device(**body.model_dump())
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@router.put("/{device_id}", response_model=schemas.Device)
async def update_device(
    device_id: str,
    body: schemas.DeviceUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(models.Device).filter(models.Device.device_id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(device, field, value)

    await db.commit()
    await db.refresh(device)
    return device


@router.delete("/all")
async def delete_all_devices(db: AsyncSession = Depends(get_db)):
    """Delete all registered devices (for test reset)."""
    result = await db.execute(select(models.Device))
    devices = result.scalars().all()
    count = len(devices)
    for d in devices:
        await db.delete(d)
    await db.commit()
    return {"success": True, "deleted": count}


@router.delete("/{device_id}")
async def delete_device(device_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Device).filter(models.Device.device_id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    await db.delete(device)
    await db.commit()
    return {"success": True}


@router.post("/heartbeat", response_model=schemas.Device)
async def device_heartbeat(
    body: schemas.DeviceHeartbeat,
    db: AsyncSession = Depends(get_db),
):
    """Brain push: create-or-update on MQTT activity.

    Creates device with minimum metadata if unknown; otherwise updates
    last_state / last_value / last_seen / battery_pct without overwriting
    user-edited fields (display_name / purpose / location / zone).
    """
    result = await db.execute(select(models.Device).filter(models.Device.device_id == body.device_id))
    device = result.scalars().first()
    now = datetime.now(UTC)

    last_seen_reported = None
    if body.last_seen_reported is not None:
        try:
            last_seen_reported = datetime.fromtimestamp(body.last_seen_reported, tz=UTC)
        except (TypeError, ValueError, OSError):
            last_seen_reported = None

    if device is None:
        device = models.Device(
            device_id=body.device_id,
            vendor=body.vendor,
            vendor_ref=body.vendor_ref,
            kind=body.kind or "actuator",
            device_class=body.device_class,
            capabilities=body.capabilities or [],
            channels=body.channels or [],
            units=body.units or {},
            zone=body.zone,
            display_name=body.display_name,
            description=body.description,
            model_id=body.model_id,
            manufacturer=body.manufacturer,
            last_state=body.last_state or {},
            last_value=body.last_value or {},
            last_seen=now,
            last_seen_reported=last_seen_reported,
            battery_pct=body.battery_pct,
            link_quality=body.link_quality,
            is_enabled=True,
        )
        db.add(device)
        logger.info(f"Auto-registered new device: {body.device_id} ({body.vendor})")
    else:
        # Refresh volatile fields only
        if body.last_state is not None:
            device.last_state = body.last_state
        if body.last_value is not None:
            device.last_value = body.last_value
        if body.battery_pct is not None:
            device.battery_pct = body.battery_pct
        if body.link_quality is not None:
            device.link_quality = body.link_quality
        if last_seen_reported is not None:
            device.last_seen_reported = last_seen_reported
        device.last_seen = now
        # Allow brain to refine type info if metadata was not user-set
        # Generic fallback values (vendor name as device_class) are overridable
        _GENERIC_CLASSES = {"zigbee", "switchbot", "tapo", "mcp", "ha", "sensor"}
        if body.vendor_ref and not device.vendor_ref:
            device.vendor_ref = body.vendor_ref
        if body.kind and body.kind != device.kind:
            # Upgrade: sensor → actuator/both when Z2M reveals it's controllable
            if device.kind == "sensor" and body.kind in ("actuator", "both"):
                device.kind = body.kind
        if body.device_class and (not device.device_class or device.device_class in _GENERIC_CLASSES):
            device.device_class = body.device_class
        if body.capabilities:
            existing = set(device.capabilities or [])
            merged = existing | set(body.capabilities)
            if merged != existing:
                device.capabilities = sorted(merged)
        if body.channels and not device.channels:
            device.channels = body.channels
        if body.units and not device.units:
            device.units = body.units
        if body.display_name and _is_placeholder_name(device.display_name, device.device_id):
            device.display_name = body.display_name
        if body.description and not device.description:
            device.description = body.description
        if body.model_id and not device.model_id:
            device.model_id = body.model_id
        if body.manufacturer and not device.manufacturer:
            device.manufacturer = body.manufacturer

    await db.commit()
    await db.refresh(device)
    return device


@router.post("/zigbee/permit_join", response_model=schemas.DeviceControlResponse)
async def zigbee_permit_join(body: schemas.ZigbeePermitJoinRequest):
    """Open or close the Z2M coordinator for new device pairing.

    Proxies to Brain, which publishes on `zigbee2mqtt/bridge/request/permit_join`.
    """
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                f"{BRAIN_URL}/devices/zigbee/permit_join",
                json={"enable": body.enable, "duration_s": body.duration_s},
                headers=_brain_auth_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp,
        ):
            data = await resp.json()
            if resp.status == 200:
                return schemas.DeviceControlResponse(
                    success=data.get("success", False),
                    result=data.get("result"),
                    error=data.get("error"),
                )
            return schemas.DeviceControlResponse(
                success=False,
                error=data.get("detail", f"HTTP {resp.status}"),
            )
    except Exception as e:
        logger.error(f"permit_join proxy failed: {e}")
        return schemas.DeviceControlResponse(success=False, error=str(e))


@router.post("/{device_id}/control", response_model=schemas.DeviceControlResponse)
async def control_device(
    device_id: str,
    body: schemas.DeviceControlRequest,
    db: AsyncSession = Depends(get_db),
):
    """Proxy a manual control request to Brain (which dispatches to bridge)."""
    result = await db.execute(select(models.Device).filter(models.Device.device_id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    if not device.is_enabled:
        raise HTTPException(status_code=400, detail=f"Device '{device_id}' is disabled")

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                f"{BRAIN_URL}/devices/control",
                json={"device_id": device_id, "action": body.action, "params": body.params},
                headers=_brain_auth_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp,
        ):
            data = await resp.json()
            if resp.status == 200:
                return schemas.DeviceControlResponse(
                    success=data.get("success", False),
                    result=data.get("result"),
                    error=data.get("error"),
                )
            return schemas.DeviceControlResponse(
                success=False,
                error=data.get("detail", f"HTTP {resp.status}"),
            )
    except Exception as e:
        logger.error(f"Control proxy failed for {device_id}: {e}")
        return schemas.DeviceControlResponse(success=False, error=str(e))
