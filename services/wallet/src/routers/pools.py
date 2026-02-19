"""Pools router — Model B: Funding pool admin API.

Admin manages cash-funded pools. External payment is out of scope;
admin records contributions after verifying payment externally.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from models import FundingPool, PoolContribution
from schemas import (
    PoolCreateRequest, PoolContributeRequest, PoolActivateRequest,
    PoolResponse, PoolContributionResponse, PoolListResponse,
)
from services.pool_service import (
    create_pool, contribute, activate_pool, get_pool_with_contributions,
)

logger = logging.getLogger(__name__)

# Admin routes
admin_router = APIRouter(prefix="/admin/pools", tags=["pools-admin"])


@admin_router.post("", response_model=PoolResponse)
async def api_create_pool(
    body: PoolCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Admin creates a funding pool."""
    try:
        pool = await create_pool(
            db,
            title=body.title,
            goal_jpy=body.goal_jpy,
            share_price=body.share_price,
            total_shares=body.total_shares,
            description=body.description,
        )
        await db.commit()
        await db.refresh(pool)
        return PoolResponse(
            id=pool.id,
            title=pool.title,
            description=pool.description,
            goal_jpy=pool.goal_jpy,
            raised_jpy=pool.raised_jpy,
            share_price=pool.share_price,
            total_shares=pool.total_shares,
            status=pool.status,
            device_id=pool.device_id,
            created_at=pool.created_at,
            contributions=[],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@admin_router.get("", response_model=List[PoolListResponse])
async def api_list_pools_admin(
    db: AsyncSession = Depends(get_db),
):
    """Admin lists all pools."""
    result = await db.execute(
        select(FundingPool).order_by(FundingPool.created_at.desc())
    )
    pools = result.scalars().all()
    return [
        PoolListResponse(
            id=p.id,
            title=p.title,
            goal_jpy=p.goal_jpy,
            raised_jpy=p.raised_jpy,
            status=p.status,
            progress_pct=round(p.raised_jpy / p.goal_jpy * 100, 1) if p.goal_jpy > 0 else 0,
            created_at=p.created_at,
        )
        for p in pools
    ]


@admin_router.get("/{pool_id}", response_model=PoolResponse)
async def api_get_pool_admin(
    pool_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Admin gets pool details with contributions."""
    pool, contributions = await get_pool_with_contributions(db, pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    return PoolResponse(
        id=pool.id,
        title=pool.title,
        description=pool.description,
        goal_jpy=pool.goal_jpy,
        raised_jpy=pool.raised_jpy,
        share_price=pool.share_price,
        total_shares=pool.total_shares,
        status=pool.status,
        device_id=pool.device_id,
        created_at=pool.created_at,
        contributions=[
            PoolContributionResponse(
                id=c.id,
                pool_id=c.pool_id,
                user_id=c.user_id,
                amount_jpy=c.amount_jpy,
                shares_allocated=c.shares_allocated,
                contributed_at=c.contributed_at,
            )
            for c in contributions
        ],
    )


@admin_router.post("/{pool_id}/contribute", response_model=PoolContributionResponse)
async def api_contribute(
    pool_id: int,
    body: PoolContributeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Admin records a cash contribution."""
    try:
        contrib = await contribute(db, pool_id, body.user_id, body.amount_jpy)
        await db.commit()
        await db.refresh(contrib)
        return contrib
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@admin_router.post("/{pool_id}/activate", response_model=PoolResponse)
async def api_activate_pool(
    pool_id: int,
    body: PoolActivateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Admin activates pool: links device and allocates shares."""
    try:
        pool = await activate_pool(db, pool_id, body.device_id)
        await db.commit()
        # Re-fetch with contributions
        pool, contributions = await get_pool_with_contributions(db, pool_id)
        return PoolResponse(
            id=pool.id,
            title=pool.title,
            description=pool.description,
            goal_jpy=pool.goal_jpy,
            raised_jpy=pool.raised_jpy,
            share_price=pool.share_price,
            total_shares=pool.total_shares,
            status=pool.status,
            device_id=pool.device_id,
            created_at=pool.created_at,
            contributions=[
                PoolContributionResponse(
                    id=c.id,
                    pool_id=c.pool_id,
                    user_id=c.user_id,
                    amount_jpy=c.amount_jpy,
                    shares_allocated=c.shares_allocated,
                    contributed_at=c.contributed_at,
                )
                for c in contributions
            ],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Public routes (read-only for supporters)
public_router = APIRouter(prefix="/pools", tags=["pools"])


@public_router.get("", response_model=List[PoolListResponse])
async def api_list_pools_public(
    db: AsyncSession = Depends(get_db),
):
    """Public pool listing (open/funded pools only)."""
    result = await db.execute(
        select(FundingPool)
        .filter(FundingPool.status.in_(["open", "funded", "active"]))
        .order_by(FundingPool.created_at.desc())
    )
    pools = result.scalars().all()
    return [
        PoolListResponse(
            id=p.id,
            title=p.title,
            goal_jpy=p.goal_jpy,
            raised_jpy=p.raised_jpy,
            status=p.status,
            progress_pct=round(p.raised_jpy / p.goal_jpy * 100, 1) if p.goal_jpy > 0 else 0,
            created_at=p.created_at,
        )
        for p in pools
    ]
