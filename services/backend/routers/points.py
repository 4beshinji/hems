from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from database import get_db
import models
import schemas

router = APIRouter(prefix="/points", tags=["points"])


@router.get("/{user_id}", response_model=List[schemas.PointLog])
async def get_point_history(
    user_id: int,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.PointLog)
        .filter(models.PointLog.user_id == user_id)
        .order_by(models.PointLog.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/{user_id}/grant", response_model=schemas.PointLog)
async def grant_points(
    user_id: int,
    body: schemas.PointLogCreate,
    db: AsyncSession = Depends(get_db),
):
    user_result = await db.execute(
        select(models.User).filter(models.User.id == user_id)
    )
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.points += body.amount
    log = models.PointLog(
        user_id=user_id,
        amount=body.amount,
        reason=body.reason,
        task_id=body.task_id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log
