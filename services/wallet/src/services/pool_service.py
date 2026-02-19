"""Pool service — Model B funding pool management.

Manages funding pools for casual supporters who contribute cash (external
payment). Admin creates pools, records contributions, and activates pools
when the funding goal is reached and a device is purchased.
"""

import logging
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Device, DeviceStake, FundingPool, PoolContribution
from services.ledger import get_or_create_wallet

logger = logging.getLogger(__name__)


async def create_pool(
    db: AsyncSession,
    title: str,
    goal_jpy: int,
    share_price: int = 100,
    total_shares: int = 100,
    description: str | None = None,
) -> FundingPool:
    """Admin creates a new funding pool."""
    if goal_jpy < 1:
        raise ValueError("goal_jpy must be positive")

    pool = FundingPool(
        title=title,
        description=description,
        goal_jpy=goal_jpy,
        share_price=share_price,
        total_shares=total_shares,
        status="open",
    )
    db.add(pool)
    await db.flush()
    logger.info("Pool created: id=%d, title=%s, goal=%d JPY", pool.id, title, goal_jpy)
    return pool


async def contribute(
    db: AsyncSession,
    pool_id: int,
    user_id: int,
    amount_jpy: int,
) -> PoolContribution:
    """Admin records a cash contribution (after external payment verification)."""
    if amount_jpy < 1:
        raise ValueError("amount_jpy must be positive")

    result = await db.execute(
        select(FundingPool).filter(FundingPool.id == pool_id)
    )
    pool = result.scalars().first()
    if not pool:
        raise ValueError(f"Pool not found: {pool_id}")
    if pool.status not in ("open", "funded"):
        raise ValueError(f"Pool is {pool.status}, cannot accept contributions")

    contribution = PoolContribution(
        pool_id=pool_id,
        user_id=user_id,
        amount_jpy=amount_jpy,
    )
    db.add(contribution)

    pool.raised_jpy += amount_jpy

    # Auto-transition to funded when goal reached
    if pool.raised_jpy >= pool.goal_jpy and pool.status == "open":
        pool.status = "funded"
        logger.info("Pool %d reached goal (%d/%d JPY)", pool_id, pool.raised_jpy, pool.goal_jpy)

    await db.flush()

    # Ensure contributor has a wallet (auto-create)
    await get_or_create_wallet(db, user_id)

    logger.info(
        "Contribution: pool=%d, user=%d, amount=%d JPY, total=%d/%d",
        pool_id, user_id, amount_jpy, pool.raised_jpy, pool.goal_jpy,
    )
    return contribution


async def activate_pool(
    db: AsyncSession,
    pool_id: int,
    device_id_str: str,
) -> FundingPool:
    """Admin activates a pool: links device and allocates shares proportionally.

    1. Link pool to device
    2. Calculate each contributor's share based on contribution ratio
    3. Create DeviceStake rows for each contributor
    4. Set pool status to 'active'
    """
    result = await db.execute(
        select(FundingPool).filter(FundingPool.id == pool_id)
    )
    pool = result.scalars().first()
    if not pool:
        raise ValueError(f"Pool not found: {pool_id}")
    if pool.status not in ("funded", "open"):
        raise ValueError(f"Pool is {pool.status}, cannot activate")

    # Find the device
    dev_result = await db.execute(
        select(Device).filter(Device.device_id == device_id_str)
    )
    device = dev_result.scalars().first()
    if not device:
        raise ValueError(f"Device not found: {device_id_str}")

    pool.device_id = device.id
    pool.status = "active"

    # Distribute shares proportionally to contribution amounts
    contrib_result = await db.execute(
        select(PoolContribution).filter(PoolContribution.pool_id == pool_id)
    )
    contributions = list(contrib_result.scalars().all())

    if not contributions:
        raise ValueError("No contributions in this pool")

    total_contributed = sum(c.amount_jpy for c in contributions)
    total_shares_to_allocate = pool.total_shares
    allocated = 0

    for contrib in contributions:
        shares = int(total_shares_to_allocate * contrib.amount_jpy / total_contributed)
        if shares < 1:
            shares = 1  # Minimum 1 share per contributor
        contrib.shares_allocated = shares

        # Create or update DeviceStake
        stake_result = await db.execute(
            select(DeviceStake).filter(
                DeviceStake.device_id == device.id,
                DeviceStake.user_id == contrib.user_id,
            )
        )
        existing_stake = stake_result.scalars().first()
        if existing_stake:
            existing_stake.shares += shares
        else:
            db.add(DeviceStake(
                device_id=device.id,
                user_id=contrib.user_id,
                shares=shares,
            ))

        # Ensure wallet exists
        await get_or_create_wallet(db, contrib.user_id)
        allocated += shares

    # Assign remainder to largest contributor (or first)
    remainder = total_shares_to_allocate - allocated
    if remainder > 0 and contributions:
        largest = max(contributions, key=lambda c: c.amount_jpy)
        largest.shares_allocated += remainder
        stake_result = await db.execute(
            select(DeviceStake).filter(
                DeviceStake.device_id == device.id,
                DeviceStake.user_id == largest.user_id,
            )
        )
        stake = stake_result.scalars().first()
        if stake:
            stake.shares += remainder

    # Update device share tracking
    device.total_shares = pool.total_shares
    device.share_price = pool.share_price
    device.available_shares = 0
    device.funding_open = False

    await db.flush()
    logger.info(
        "Pool %d activated: device=%s, %d contributors, %d shares allocated",
        pool_id, device_id_str, len(contributions), allocated + remainder,
    )
    return pool


async def get_pool_with_contributions(
    db: AsyncSession,
    pool_id: int,
) -> tuple[FundingPool | None, List[PoolContribution]]:
    """Get pool details with all contributions."""
    result = await db.execute(
        select(FundingPool).filter(FundingPool.id == pool_id)
    )
    pool = result.scalars().first()
    if not pool:
        return None, []

    contrib_result = await db.execute(
        select(PoolContribution)
        .filter(PoolContribution.pool_id == pool_id)
        .order_by(PoolContribution.contributed_at)
    )
    contributions = list(contrib_result.scalars().all())
    return pool, contributions
