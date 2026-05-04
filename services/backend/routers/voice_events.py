from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
import schemas
from database import get_db

router = APIRouter(prefix="/voice-events", tags=["voice-events"])


@router.post("/", response_model=schemas.VoiceEvent)
async def create_voice_event(event: schemas.VoiceEventCreate, db: AsyncSession = Depends(get_db)):
    db_event = models.VoiceEvent(
        message=event.message,
        audio_url=event.audio_url,
        zone=event.zone,
        tone=event.tone,
        motion_id=event.motion_id,
    )
    db.add(db_event)
    await db.commit()
    await db.refresh(db_event)
    return db_event


@router.get("/recent", response_model=list[schemas.VoiceEvent])
async def get_recent_voice_events(db: AsyncSession = Depends(get_db)):
    max_age = datetime.now(UTC) - timedelta(hours=24)
    result = await db.execute(
        select(models.VoiceEvent)
        .where(models.VoiceEvent.created_at >= max_age)
        .order_by(models.VoiceEvent.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/alerts", response_model=list[schemas.VoiceEvent])
async def get_recent_alerts(hours: int = 168, db: AsyncSession = Depends(get_db)):
    """Recent alert-toned voice events for the alert history panel."""
    hours = max(1, min(hours, 720))
    max_age = datetime.now(UTC) - timedelta(hours=hours)
    result = await db.execute(
        select(models.VoiceEvent)
        .where(models.VoiceEvent.created_at >= max_age)
        .where(models.VoiceEvent.tone == "alert")
        .order_by(models.VoiceEvent.created_at.desc())
        .limit(200)
    )
    return result.scalars().all()
