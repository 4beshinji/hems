"""Stakes router — Model A: SOMS staking API.

Allows device owners to open funding, and investors to buy/return shares.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from models import Device, DeviceStake, RewardRate
from schemas import (
    FundingOpenRequest, FundingCloseRequest,
    StakeBuyRequest, StakeReturnRequest,
    StakeResponse, DeviceFundingResponse, DeviceResponse,
    PortfolioEntry, PortfolioResponse,
)
from services.stake_service import (
    open_funding, close_funding, buy_shares, return_shares,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["stakes"])


def _stake_to_response(stake: DeviceStake, total_shares: int) -> StakeResponse:
    pct = (stake.shares / total_shares * 100) if total_shares > 0 else 0.0
    return StakeResponse(
        id=stake.id,
        device_id=stake.device_id,
        user_id=stake.user_id,
        shares=stake.shares,
        percentage=round(pct, 2),
        acquired_at=stake.acquired_at,
    )


@router.post("/{device_id}/funding/open", response_model=DeviceResponse)
async def api_open_funding(
    device_id: str,
    body: FundingOpenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Owner opens funding: list shares for sale."""
    try:
        device = await open_funding(
            db, device_id, body.owner_id, body.shares_to_list, body.share_price,
        )
        await db.commit()
        await db.refresh(device)
        return device
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{device_id}/funding/close", response_model=DeviceResponse)
async def api_close_funding(
    device_id: str,
    body: FundingCloseRequest,
    db: AsyncSession = Depends(get_db),
):
    """Owner closes funding. Existing stakes remain."""
    try:
        device = await close_funding(db, device_id, body.owner_id)
        await db.commit()
        await db.refresh(device)
        return device
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{device_id}/stakes/buy", response_model=StakeResponse)
async def api_buy_shares(
    device_id: str,
    body: StakeBuyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Investor buys shares with SOMS."""
    try:
        stake = await buy_shares(db, device_id, body.user_id, body.shares)
        await db.commit()
        await db.refresh(stake)
        # Need device total_shares for percentage
        dev_result = await db.execute(
            select(Device).filter(Device.device_id == device_id)
        )
        device = dev_result.scalars().first()
        return _stake_to_response(stake, device.total_shares if device else 100)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{device_id}/stakes/return")
async def api_return_shares(
    device_id: str,
    body: StakeReturnRequest,
    db: AsyncSession = Depends(get_db),
):
    """Investor returns shares. System buys back at share_price."""
    try:
        stake = await return_shares(db, device_id, body.user_id, body.shares)
        await db.commit()
        if stake:
            await db.refresh(stake)
            dev_result = await db.execute(
                select(Device).filter(Device.device_id == device_id)
            )
            device = dev_result.scalars().first()
            return _stake_to_response(stake, device.total_shares if device else 100)
        return {"detail": "All shares returned, stake removed"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{device_id}/stakes", response_model=DeviceFundingResponse)
async def api_get_device_stakes(
    device_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all stakeholders for a device."""
    result = await db.execute(
        select(Device).filter(Device.device_id == device_id)
    )
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    stakes_result = await db.execute(
        select(DeviceStake).filter(DeviceStake.device_id == device.id)
    )
    stakes = list(stakes_result.scalars().all())

    # Estimated reward per hour
    rate_result = await db.execute(
        select(RewardRate).filter(RewardRate.device_type == device.device_type)
    )
    rate = rate_result.scalars().first()
    estimated_reward = rate.rate_per_hour if rate else 0

    return DeviceFundingResponse(
        device_id=device.device_id,
        total_shares=device.total_shares,
        available_shares=device.available_shares,
        share_price=device.share_price,
        funding_open=device.funding_open,
        stakeholders=[
            _stake_to_response(s, device.total_shares) for s in stakes
        ],
        estimated_reward_per_hour=estimated_reward,
    )


# User portfolio — mounted under /users/ prefix in main.py via separate router
portfolio_router = APIRouter(prefix="/users", tags=["stakes"])


@portfolio_router.get("/{user_id}/portfolio", response_model=PortfolioResponse)
async def api_get_portfolio(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get all stakes for a user across all devices."""
    stakes_result = await db.execute(
        select(DeviceStake).filter(DeviceStake.user_id == user_id)
    )
    stakes = list(stakes_result.scalars().all())

    entries = []
    total_reward = 0

    for stake in stakes:
        dev_result = await db.execute(
            select(Device).filter(Device.id == stake.device_id)
        )
        device = dev_result.scalars().first()
        if not device:
            continue

        rate_result = await db.execute(
            select(RewardRate).filter(RewardRate.device_type == device.device_type)
        )
        rate = rate_result.scalars().first()
        device_reward = rate.rate_per_hour if rate else 0
        user_reward = int(device_reward * stake.shares / device.total_shares) if device.total_shares > 0 else 0
        total_reward += user_reward

        pct = (stake.shares / device.total_shares * 100) if device.total_shares > 0 else 0.0
        entries.append(PortfolioEntry(
            device_id=device.device_id,
            device_type=device.device_type,
            shares=stake.shares,
            total_shares=device.total_shares,
            percentage=round(pct, 2),
            estimated_reward_per_hour=user_reward,
        ))

    return PortfolioResponse(
        user_id=user_id,
        stakes=entries,
        total_estimated_reward_per_hour=total_reward,
    )
