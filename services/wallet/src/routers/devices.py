import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func as sa_func
from typing import List

from database import get_db
from models import Device, RewardRate
from schemas import (
    DeviceCreate, DeviceUpdate, DeviceResponse,
    DeviceXpGrantRequest, DeviceXpResponse, DeviceXpStatsResponse,
    HeartbeatResponse, HeartbeatRequest, UtilityScoreUpdate,
)
from services.ledger import transfer, SYSTEM_USER_ID
from services.xp_scorer import grant_xp_to_zone, compute_reward_multiplier, find_zone_devices
from services.stake_service import distribute_reward

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/", response_model=DeviceResponse)
async def register_device(body: DeviceCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(Device).filter(Device.device_id == body.device_id)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Device already registered")

    device = Device(
        device_id=body.device_id,
        owner_id=body.owner_id,
        device_type=body.device_type,
        display_name=body.display_name,
        topic_prefix=body.topic_prefix,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@router.get("/", response_model=List[DeviceResponse])
async def list_devices(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).order_by(Device.registered_at.desc()))
    return result.scalars().all()


@router.put("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    body: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device).filter(Device.device_id == device_id)
    )
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if body.display_name is not None:
        device.display_name = body.display_name
    if body.is_active is not None:
        device.is_active = body.is_active
    if body.topic_prefix is not None:
        device.topic_prefix = body.topic_prefix

    await db.commit()
    await db.refresh(device)
    return device


@router.post("/xp-grant", response_model=DeviceXpResponse)
async def xp_grant(body: DeviceXpGrantRequest, db: AsyncSession = Depends(get_db)):
    """Grant XP to all active devices in a zone."""
    devices_awarded, total_xp, device_ids = await grant_xp_to_zone(
        db,
        zone=body.zone,
        task_id=body.task_id,
        xp_amount=body.xp_amount,
        event_type=body.event_type,
    )
    await db.commit()
    return DeviceXpResponse(
        devices_awarded=devices_awarded,
        total_xp_granted=total_xp,
        device_ids=device_ids,
    )


@router.post("/{device_id}/heartbeat", response_model=HeartbeatResponse)
async def device_heartbeat(
    device_id: str,
    body: HeartbeatRequest = None,
    db: AsyncSession = Depends(get_db),
):
    """Record device heartbeat and auto-grant infrastructure reward if eligible.

    Compares last_heartbeat_at with now to determine uptime since last beat.
    If the device has been active longer than min_uptime_for_reward for its
    device_type, grant a prorated infrastructure reward proportionally to
    all stakeholders (or 100% to owner if no stakes exist).

    Optional body fields update device metrics from Brain heartbeat.
    """
    result = await db.execute(
        select(Device).filter(Device.device_id == device_id)
    )
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.is_active:
        raise HTTPException(status_code=400, detail="Device is inactive")

    # Update device metrics from optional body
    if body:
        if body.power_mode is not None:
            device.power_mode = body.power_mode
        if body.battery_pct is not None:
            device.battery_pct = body.battery_pct
        if body.hops_to_mqtt is not None:
            device.hops_to_mqtt = body.hops_to_mqtt
        if body.utility_score is not None:
            device.utility_score = max(0.5, min(body.utility_score, 2.0))

    now = sa_func.now()
    prev_heartbeat = device.last_heartbeat_at
    device.last_heartbeat_at = now
    await db.flush()
    # Re-read to get the DB-resolved timestamp
    await db.refresh(device)

    reward_granted = 0
    uptime_seconds = 0

    if prev_heartbeat is not None:
        delta = device.last_heartbeat_at - prev_heartbeat
        uptime_seconds = int(delta.total_seconds())

        # Look up reward rate for this device type
        rate_result = await db.execute(
            select(RewardRate).filter(RewardRate.device_type == device.device_type)
        )
        rate = rate_result.scalars().first()

        if rate and uptime_seconds >= rate.min_uptime_for_reward:
            # Prorate: rate_per_hour * (uptime_seconds / 3600)
            reward_granted = int(rate.rate_per_hour * uptime_seconds / 3600)
            if reward_granted > 0:
                try:
                    ts = int(device.last_heartbeat_at.timestamp())
                    ref_prefix = f"infra:{device.device_id}:{ts}"
                    await distribute_reward(db, device, reward_granted, ref_prefix)
                except ValueError as e:
                    logger.warning("Heartbeat reward skip %s: %s", device_id, e)
                    reward_granted = 0

    await db.commit()
    return HeartbeatResponse(
        device_id=device.device_id,
        last_heartbeat_at=device.last_heartbeat_at,
        reward_granted=reward_granted,
        uptime_seconds=uptime_seconds,
    )


@router.post("/{device_id}/utility-score")
async def update_utility_score(
    device_id: str,
    body: UtilityScoreUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Brain updates a device's utility_score (clamped to 0.5-2.0)."""
    result = await db.execute(
        select(Device).filter(Device.device_id == device_id)
    )
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.utility_score = max(0.5, min(body.score, 2.0))
    await db.commit()
    return {"device_id": device_id, "utility_score": device.utility_score}


@router.get("/zone-multiplier/{zone}")
async def get_zone_multiplier(zone: str, db: AsyncSession = Depends(get_db)):
    """Get the average reward multiplier for devices in a zone."""
    devices = await find_zone_devices(db, zone)
    if not devices:
        return {"zone": zone, "multiplier": 1.0, "device_count": 0, "avg_xp": 0}

    avg_xp = sum(d.xp for d in devices) / len(devices)
    multiplier = compute_reward_multiplier(int(avg_xp))
    return {
        "zone": zone,
        "multiplier": multiplier,
        "device_count": len(devices),
        "avg_xp": int(avg_xp),
    }
