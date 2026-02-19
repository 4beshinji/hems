"""XP scoring service — distributes XP to devices by zone.

When a task is created or completed for a zone, all active registered
devices whose topic_prefix matches that zone receive XP.  This creates
an incentive for device owners to optimise placement: better sensors
→ more useful data → more tasks → more XP → higher dynamic rewards.

Zone matching uses the MQTT topic convention:
    topic_prefix LIKE 'office/{zone}/%'
"""

import logging
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Device

logger = logging.getLogger(__name__)

# Default XP amounts per event
DEFAULT_XP_TASK_CREATED = 10
DEFAULT_XP_TASK_COMPLETED = 20


async def find_zone_devices(
    db: AsyncSession,
    zone: str,
) -> List[Device]:
    """Find all active devices registered to a zone via topic_prefix."""
    pattern = f"office/{zone}/%"
    result = await db.execute(
        select(Device).filter(
            Device.is_active == True,  # noqa: E712
            Device.topic_prefix.like(pattern),
        )
    )
    return list(result.scalars().all())


async def grant_xp_to_zone(
    db: AsyncSession,
    zone: str,
    task_id: int,
    xp_amount: int,
    event_type: str = "task_created",
) -> Tuple[int, int, List[str]]:
    """Grant XP to all active devices in a zone.

    Args:
        zone: Zone identifier (e.g. "main", "kitchen")
        task_id: The task that triggered the XP grant
        xp_amount: XP per device
        event_type: "task_created" or "task_completed"

    Returns:
        (devices_awarded, total_xp_granted, device_ids)
    """
    devices = await find_zone_devices(db, zone)

    if not devices:
        logger.info(
            "XP grant (%s) for zone=%s task=%d: no devices found",
            event_type, zone, task_id,
        )
        return 0, 0, []

    device_ids = []
    for device in devices:
        device.xp += xp_amount
        device_ids.append(device.device_id)

    total_xp = xp_amount * len(devices)
    await db.flush()

    logger.info(
        "XP grant (%s) for zone=%s task=%d: %d devices × %d XP = %d total [%s]",
        event_type, zone, task_id, len(devices), xp_amount, total_xp,
        ", ".join(device_ids),
    )
    return len(devices), total_xp, device_ids


def compute_reward_multiplier(device_xp: int) -> float:
    """Compute dynamic reward multiplier from device XP.

    Formula: 1.0 + (xp / 1000) * 0.5, capped at 3.0×
    - 0 XP    → 1.0×
    - 1000 XP → 1.5×
    - 2000 XP → 2.0×
    - 4000 XP → 3.0× (cap)
    """
    multiplier = 1.0 + (device_xp / 1000.0) * 0.5
    return min(multiplier, 3.0)


def compute_contribution_weight(device: Device) -> float:
    """Compute total contribution weight: hardware_weight × utility_score.

    hardware_weight (static, based on physical characteristics):
      Base: 1.0 (AC power, 0 hops)
      +0.5: Battery-powered (DEEP_SLEEP / ULTRA_LOW / LIGHT_SLEEP)
      +0.2/hop: Relay burden (max +0.6)
      Range: 1.0 ~ 2.0

    utility_score (dynamic, from Brain):
      Range: 0.5 ~ 2.0

    total_weight Range: 0.5 ~ 4.0
    """
    hw = 1.0
    if device.power_mode in ("DEEP_SLEEP", "ULTRA_LOW", "LIGHT_SLEEP"):
        hw += 0.5
    hops = device.hops_to_mqtt or 0
    hw += min(hops * 0.2, 0.6)
    hw = min(hw, 2.0)

    utility = device.utility_score if device.utility_score else 1.0
    return hw * utility


async def grant_xp_to_zone_weighted(
    db: AsyncSession,
    zone: str,
    task_id: int,
    base_xp: int,
    event_type: str = "task_created",
) -> Tuple[int, int, List[str]]:
    """Grant weighted XP to all active devices in a zone.

    Each device receives base_xp * contribution_weight.

    Returns:
        (devices_awarded, total_xp_granted, device_ids)
    """
    devices = await find_zone_devices(db, zone)

    if not devices:
        logger.info(
            "Weighted XP grant (%s) for zone=%s task=%d: no devices found",
            event_type, zone, task_id,
        )
        return 0, 0, []

    device_ids = []
    total_xp = 0
    for device in devices:
        w = compute_contribution_weight(device)
        xp_grant = int(base_xp * w)
        device.xp += xp_grant
        device_ids.append(device.device_id)
        total_xp += xp_grant

    await db.flush()

    logger.info(
        "Weighted XP grant (%s) for zone=%s task=%d: %d devices, %d total XP [%s]",
        event_type, zone, task_id, len(devices), total_xp,
        ", ".join(device_ids),
    )
    return len(devices), total_xp, device_ids
