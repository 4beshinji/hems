"""Stake service — device share ownership and proportional reward distribution.

Handles Model A (SOMS staking): users purchase shares in devices and receive
proportional infrastructure rewards on each heartbeat.
"""

import logging
import time
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models import Device, DeviceStake
from services.ledger import transfer, SYSTEM_USER_ID

logger = logging.getLogger(__name__)


async def _get_device_by_str_id(db: AsyncSession, device_id_str: str) -> Device:
    """Look up a device by its string device_id. Raises ValueError if not found."""
    result = await db.execute(
        select(Device).filter(Device.device_id == device_id_str)
    )
    device = result.scalars().first()
    if not device:
        raise ValueError(f"Device not found: {device_id_str}")
    return device


async def open_funding(
    db: AsyncSession,
    device_id_str: str,
    owner_id: int,
    shares_to_list: int,
    share_price: int,
) -> Device:
    """Owner opens funding: creates owner's DeviceStake and lists shares for sale."""
    device = await _get_device_by_str_id(db, device_id_str)

    if device.owner_id != owner_id:
        raise ValueError("Only the device owner can open funding")
    if device.funding_open:
        raise ValueError("Funding is already open")
    if shares_to_list < 1 or shares_to_list >= device.total_shares:
        raise ValueError(
            f"shares_to_list must be between 1 and {device.total_shares - 1}"
        )
    if share_price < 1:
        raise ValueError("share_price must be positive")

    device.share_price = share_price
    device.available_shares = shares_to_list
    device.funding_open = True

    # Create owner's stake for the remaining shares (explicit, not implicit)
    owner_shares = device.total_shares - shares_to_list
    result = await db.execute(
        select(DeviceStake).filter(
            DeviceStake.device_id == device.id,
            DeviceStake.user_id == owner_id,
        )
    )
    existing_stake = result.scalars().first()
    if existing_stake:
        existing_stake.shares = owner_shares
    else:
        db.add(DeviceStake(
            device_id=device.id,
            user_id=owner_id,
            shares=owner_shares,
        ))

    await db.flush()
    logger.info(
        "Funding opened: device=%s, listed=%d shares @ %d/share, owner keeps %d",
        device_id_str, shares_to_list, share_price, owner_shares,
    )
    return device


async def close_funding(
    db: AsyncSession,
    device_id_str: str,
    owner_id: int,
) -> Device:
    """Owner closes funding. Existing stakes remain; no new purchases."""
    device = await _get_device_by_str_id(db, device_id_str)

    if device.owner_id != owner_id:
        raise ValueError("Only the device owner can close funding")
    if not device.funding_open:
        raise ValueError("Funding is not open")

    device.funding_open = False
    # Reclaim unsold shares to owner's stake
    if device.available_shares > 0:
        result = await db.execute(
            select(DeviceStake).filter(
                DeviceStake.device_id == device.id,
                DeviceStake.user_id == owner_id,
            )
        )
        owner_stake = result.scalars().first()
        if owner_stake:
            owner_stake.shares += device.available_shares
        device.available_shares = 0

    await db.flush()
    logger.info("Funding closed: device=%s", device_id_str)
    return device


async def buy_shares(
    db: AsyncSession,
    device_id_str: str,
    user_id: int,
    shares_count: int,
) -> DeviceStake:
    """Investor buys shares. SOMS transferred to owner as hardware cost recovery."""
    if shares_count < 1:
        raise ValueError("Must buy at least 1 share")

    device = await _get_device_by_str_id(db, device_id_str)

    if not device.funding_open:
        raise ValueError("Funding is not open for this device")
    if shares_count > device.available_shares:
        raise ValueError(
            f"Only {device.available_shares} shares available"
        )

    cost = shares_count * device.share_price
    epoch = int(time.time())
    ref = f"stake:buy:{device.device_id}:{user_id}:{epoch}"

    # Transfer SOMS from buyer to owner
    await transfer(
        db,
        from_user_id=user_id,
        to_user_id=device.owner_id,
        amount=cost,
        transaction_type="STAKE_PURCHASE",
        description=f"Share purchase: {shares_count} shares of {device.device_id}",
        reference_id=ref,
    )

    # Update or create stake
    result = await db.execute(
        select(DeviceStake).filter(
            DeviceStake.device_id == device.id,
            DeviceStake.user_id == user_id,
        )
    )
    stake = result.scalars().first()
    if stake:
        stake.shares += shares_count
    else:
        stake = DeviceStake(
            device_id=device.id,
            user_id=user_id,
            shares=shares_count,
        )
        db.add(stake)

    device.available_shares -= shares_count
    await db.flush()

    logger.info(
        "Shares bought: device=%s, user=%d, shares=%d, cost=%d",
        device_id_str, user_id, shares_count, cost,
    )
    return stake


async def return_shares(
    db: AsyncSession,
    device_id_str: str,
    user_id: int,
    shares_count: int,
) -> Optional[DeviceStake]:
    """Investor returns shares. System buys back at share_price (liquidity guarantee)."""
    if shares_count < 1:
        raise ValueError("Must return at least 1 share")

    device = await _get_device_by_str_id(db, device_id_str)

    result = await db.execute(
        select(DeviceStake).filter(
            DeviceStake.device_id == device.id,
            DeviceStake.user_id == user_id,
        )
    )
    stake = result.scalars().first()
    if not stake:
        raise ValueError("No stake found for this user/device")
    if stake.shares < shares_count:
        raise ValueError(f"Only {stake.shares} shares held")

    # Owner cannot return shares (they are the residual holder)
    if user_id == device.owner_id:
        raise ValueError("Owner cannot return shares; close funding instead")

    refund_amount = shares_count * device.share_price
    epoch = int(time.time())
    ref = f"stake:return:{device.device_id}:{user_id}:{epoch}"

    # System buys back
    await transfer(
        db,
        from_user_id=SYSTEM_USER_ID,
        to_user_id=user_id,
        amount=refund_amount,
        transaction_type="STAKE_REFUND",
        description=f"Share return: {shares_count} shares of {device.device_id}",
        reference_id=ref,
    )

    stake.shares -= shares_count
    device.available_shares += shares_count

    # Remove stake row if zero
    if stake.shares == 0:
        await db.delete(stake)
        stake = None

    await db.flush()
    logger.info(
        "Shares returned: device=%s, user=%d, shares=%d, refund=%d",
        device_id_str, user_id, shares_count, refund_amount,
    )
    return stake


async def distribute_reward(
    db: AsyncSession,
    device: Device,
    reward_amount: int,
    reference_prefix: str,
) -> dict:
    """Distribute heartbeat reward proportionally to all stakeholders.

    If no stakes exist, 100% goes to owner (backward compatible).
    Fractional remainder goes to owner.

    Returns:
        {"distributions": [{"user_id": int, "amount": int, "shares": int}]}
    """
    result = await db.execute(
        select(DeviceStake).filter(DeviceStake.device_id == device.id)
    )
    stakes = list(result.scalars().all())

    distributions = []

    if not stakes:
        # No stakes at all — 100% to owner (backward compatible)
        ref = f"{reference_prefix}:{device.owner_id}"
        try:
            await transfer(
                db,
                from_user_id=SYSTEM_USER_ID,
                to_user_id=device.owner_id,
                amount=reward_amount,
                transaction_type="INFRASTRUCTURE_REWARD",
                description=f"Infra reward: {device.device_id}",
                reference_id=ref,
            )
            distributions.append({
                "user_id": device.owner_id,
                "amount": reward_amount,
                "shares": device.total_shares,
            })
        except ValueError as e:
            logger.warning("Reward skip (owner %d): %s", device.owner_id, e)
        return {"distributions": distributions}

    # Proportional distribution
    total_staked = sum(s.shares for s in stakes)
    distributed = 0

    for stake in stakes:
        share_reward = int(reward_amount * stake.shares / total_staked)
        if share_reward <= 0:
            continue
        ref = f"{reference_prefix}:{stake.user_id}"
        try:
            await transfer(
                db,
                from_user_id=SYSTEM_USER_ID,
                to_user_id=stake.user_id,
                amount=share_reward,
                transaction_type="INFRASTRUCTURE_REWARD",
                description=f"Infra reward: {device.device_id} ({stake.shares}/{total_staked} shares)",
                reference_id=ref,
            )
            distributed += share_reward
            distributions.append({
                "user_id": stake.user_id,
                "amount": share_reward,
                "shares": stake.shares,
            })
        except ValueError as e:
            logger.warning("Reward skip (user %d): %s", stake.user_id, e)

    # Remainder to owner
    remainder = reward_amount - distributed
    if remainder > 0:
        ref = f"{reference_prefix}:{device.owner_id}:remainder"
        try:
            await transfer(
                db,
                from_user_id=SYSTEM_USER_ID,
                to_user_id=device.owner_id,
                amount=remainder,
                transaction_type="INFRASTRUCTURE_REWARD",
                description=f"Infra reward remainder: {device.device_id}",
                reference_id=ref,
            )
            # Add to existing owner distribution or create new
            owner_dist = next(
                (d for d in distributions if d["user_id"] == device.owner_id), None
            )
            if owner_dist:
                owner_dist["amount"] += remainder
            else:
                distributions.append({
                    "user_id": device.owner_id,
                    "amount": remainder,
                    "shares": 0,
                })
        except ValueError as e:
            logger.warning("Remainder skip (owner %d): %s", device.owner_id, e)

    return {"distributions": distributions}
