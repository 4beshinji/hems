"""
Device Registry — unified sensor + actuator CRUD.

Brain pushes heartbeats on MQTT-observed devices (auto-register).
Frontend performs CRUD on metadata (display_name / purpose / zone / ...).
Control requests are proxied to Brain which dispatches to the vendor bridge.
"""
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
import models
import schemas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])

BRAIN_URL = os.getenv("BRAIN_CHAT_URL", "http://brain:8080")
HEMS_API_KEY = os.getenv("HEMS_API_KEY", "")
_AUTH_HEADERS = {"Authorization": f"Bearer {HEMS_API_KEY}"} if HEMS_API_KEY else {}


def _apply_update(device: models.Device, updates: dict) -> None:
    for field, value in updates.items():
        if value is not None or field in ("notes", "purpose", "location", "description",
                                          "display_name", "metadata_json"):
            setattr(device, field, value)


@router.get("/", response_model=List[schemas.Device])
async def list_devices(
    kind: Optional[str] = Query(None, description="sensor|actuator|both"),
    vendor: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
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
    if enabled_only:
        query = query.filter(models.Device.is_enabled == True)
    query = query.order_by(models.Device.zone, models.Device.device_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{device_id}", response_model=schemas.Device)
async def get_device(device_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.Device).filter(models.Device.device_id == device_id)
    )
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return device


@router.post("/", response_model=schemas.Device)
async def create_device(body: schemas.DeviceCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(models.Device).filter(models.Device.device_id == body.device_id)
    )
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
    result = await db.execute(
        select(models.Device).filter(models.Device.device_id == device_id)
    )
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(device, field, value)

    await db.commit()
    await db.refresh(device)
    return device


@router.delete("/{device_id}")
async def delete_device(device_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.Device).filter(models.Device.device_id == device_id)
    )
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
    result = await db.execute(
        select(models.Device).filter(models.Device.device_id == body.device_id)
    )
    device = result.scalars().first()
    now = datetime.now(timezone.utc)

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
            last_state=body.last_state or {},
            last_value=body.last_value or {},
            last_seen=now,
            battery_pct=body.battery_pct,
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
        device.last_seen = now
        # Allow brain to refine type info if metadata was not user-set
        if body.vendor_ref and not device.vendor_ref:
            device.vendor_ref = body.vendor_ref
        if body.device_class and not device.device_class:
            device.device_class = body.device_class
        if body.capabilities and not device.capabilities:
            device.capabilities = body.capabilities
        if body.channels and not device.channels:
            device.channels = body.channels
        if body.units and not device.units:
            device.units = body.units

    await db.commit()
    await db.refresh(device)
    return device


@router.post("/zigbee/permit_join", response_model=schemas.DeviceControlResponse)
async def zigbee_permit_join(body: schemas.ZigbeePermitJoinRequest):
    """Open or close the Z2M coordinator for new device pairing.

    Proxies to Brain, which publishes on `zigbee2mqtt/bridge/request/permit_join`.
    """
    try:
        async with aiohttp.ClientSession(headers=_AUTH_HEADERS) as session:
            async with session.post(
                f"{BRAIN_URL}/devices/zigbee/permit_join",
                json={"enable": body.enable, "duration_s": body.duration_s},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
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
    result = await db.execute(
        select(models.Device).filter(models.Device.device_id == device_id)
    )
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    if not device.is_enabled:
        raise HTTPException(status_code=400, detail=f"Device '{device_id}' is disabled")

    try:
        async with aiohttp.ClientSession(headers=_AUTH_HEADERS) as session:
            async with session.post(
                f"{BRAIN_URL}/devices/control",
                json={"device_id": device_id, "action": body.action, "params": body.params},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
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
