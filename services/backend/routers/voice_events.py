from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
from typing import List

from database import get_db
import models
import schemas

router = APIRouter(prefix="/voice-events", tags=["voice-events"])


@router.post("/", response_model=schemas.VoiceEvent)
async def create_voice_event(event: schemas.VoiceEventCreate, db: AsyncSession = Depends(get_db)):
    db_event = models.VoiceEvent(
        message=event.message,
        audio_url=event.audio_url,
        zone=event.zone,
        tone=event.tone,
    )
    db.add(db_event)
    await db.commit()
    await db.refresh(db_event)
    return db_event


@router.get("/recent", response_model=List[schemas.VoiceEvent])
async def get_recent_voice_events(db: AsyncSession = Depends(get_db)):
    max_age = datetime.now(timezone.utc) - timedelta(minutes=5)
    result = await db.execute(
        select(models.VoiceEvent)
        .where(models.VoiceEvent.created_at >= max_age)
        .order_by(models.VoiceEvent.created_at.desc())
    )
    return result.scalars().all()
