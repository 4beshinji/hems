import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from database import get_db
from models import SupplyStats, RewardRate
from schemas import SupplyResponse, RewardRateResponse, RewardRateUpdate
from services.demurrage import apply_demurrage

router = APIRouter(tags=["admin"])

# In-memory TTL cache for supply stats (avoid DB hit every request)
_supply_cache: dict = {"data": None, "expires_at": 0.0}
_SUPPLY_CACHE_TTL = 60  # seconds


@router.get("/supply", response_model=SupplyResponse)
async def get_supply(db: AsyncSession = Depends(get_db)):
    now = time.monotonic()
    if _supply_cache["data"] is not None and now < _supply_cache["expires_at"]:
        return _supply_cache["data"]

    result = await db.execute(select(SupplyStats))
    stats = result.scalars().first()
    if not stats:
        resp = SupplyResponse(total_issued=0, total_burned=0, circulating=0)
    else:
        resp = SupplyResponse.model_validate(stats)

    _supply_cache["data"] = resp
    _supply_cache["expires_at"] = now + _SUPPLY_CACHE_TTL
    return resp


@router.post("/demurrage/trigger")
async def trigger_demurrage():
    """Manually trigger a demurrage cycle (admin/testing use)."""
    await apply_demurrage()
    # Invalidate supply cache after demurrage burns
    _supply_cache["data"] = None
    _supply_cache["expires_at"] = 0.0
    return {"status": "ok"}


@router.get("/reward-rates", response_model=List[RewardRateResponse])
async def list_reward_rates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RewardRate).order_by(RewardRate.device_type))
    return result.scalars().all()


@router.put("/reward-rates/{device_type}", response_model=RewardRateResponse)
async def update_reward_rate(
    device_type: str,
    body: RewardRateUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RewardRate).filter(RewardRate.device_type == device_type)
    )
    rate = result.scalars().first()
    if not rate:
        raise HTTPException(status_code=404, detail="Reward rate not found")

    rate.rate_per_hour = body.rate_per_hour
    if body.min_uptime_for_reward is not None:
        rate.min_uptime_for_reward = body.min_uptime_for_reward

    await db.commit()
    await db.refresh(rate)
    return rate
