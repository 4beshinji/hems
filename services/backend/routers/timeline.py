import logging
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from sqlalchemy.sql import func

from database import get_db
import models
import schemas

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_USER = os.getenv("MQTT_USER", "hems")
MQTT_PASS = os.getenv("MQTT_PASS", "")

TZ_NAME = os.getenv("TZ", "Asia/Tokyo")
try:
    LOCAL_TZ = ZoneInfo(TZ_NAME)
except Exception:
    LOCAL_TZ = ZoneInfo("Asia/Tokyo")

router = APIRouter(prefix="/timeline", tags=["timeline"])


def _today_str() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


def _publish_timeline_today(date: str, blocks: list[dict]):
    topic = "hems/timeline/today"
    payload = json.dumps(
        {
            "date": date,
            "blocks": blocks,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        ensure_ascii=False,
        default=str,
    )
    try:
        import paho.mqtt.publish as mqtt_publish
        mqtt_publish.single(
            topic, payload, hostname=MQTT_BROKER,
            auth={"username": MQTT_USER, "password": MQTT_PASS},
            retain=True,
        )
    except Exception as e:
        logger.warning("MQTT publish failed for timeline/today: %s", e)


def _block_to_response(b: models.ScheduledBlock) -> schemas.ScheduledBlock:
    return schemas.ScheduledBlock(
        id=b.id,
        date=b.date,
        start_ts=b.start_ts,
        end_ts=b.end_ts,
        kind=b.kind,
        ref_task_id=b.ref_task_id,
        ref_calendar_event_id=b.ref_calendar_event_id,
        title=b.title,
        location=b.location,
        is_locked=b.is_locked,
        travel_buffer_minutes=b.travel_buffer_minutes,
        generated_at=b.generated_at,
    )


async def _fetch_blocks_for_date(db: AsyncSession, date: str) -> list[models.ScheduledBlock]:
    q = (
        select(models.ScheduledBlock)
        .filter(models.ScheduledBlock.date == date)
        .order_by(models.ScheduledBlock.start_ts)
    )
    r = await db.execute(q)
    return list(r.scalars().all())


@router.get("/today", response_model=schemas.TimelineResponse)
async def get_timeline_today(db: AsyncSession = Depends(get_db)):
    date = _today_str()
    blocks = await _fetch_blocks_for_date(db, date)
    return schemas.TimelineResponse(
        date=date,
        blocks=[_block_to_response(b) for b in blocks],
        generated_at=blocks[0].generated_at if blocks else None,
    )


@router.get("/day", response_model=schemas.TimelineResponse)
async def get_timeline_day(date: str, db: AsyncSession = Depends(get_db)):
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    blocks = await _fetch_blocks_for_date(db, date)
    return schemas.TimelineResponse(
        date=date,
        blocks=[_block_to_response(b) for b in blocks],
        generated_at=blocks[0].generated_at if blocks else None,
    )


@router.post("/regenerate", response_model=schemas.TimelineResponse)
async def regenerate_timeline(
    body: schemas.TimelineRegenerate,
    db: AsyncSession = Depends(get_db),
):
    """Wipe blocks for body.date and bulk insert fresh blocks. Called by brain."""
    try:
        datetime.strptime(body.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    await db.execute(
        delete(models.ScheduledBlock).where(models.ScheduledBlock.date == body.date)
    )

    for block in body.blocks:
        db.add(
            models.ScheduledBlock(
                date=body.date,
                start_ts=block.start_ts,
                end_ts=block.end_ts,
                kind=block.kind,
                ref_task_id=block.ref_task_id,
                ref_calendar_event_id=block.ref_calendar_event_id,
                title=block.title,
                location=block.location,
                is_locked=block.is_locked,
                travel_buffer_minutes=block.travel_buffer_minutes,
            )
        )
    await db.commit()

    blocks = await _fetch_blocks_for_date(db, body.date)
    response_blocks = [_block_to_response(b) for b in blocks]

    if body.date == _today_str():
        _publish_timeline_today(
            body.date,
            [b.model_dump(mode="json") for b in response_blocks],
        )

    return schemas.TimelineResponse(
        date=body.date,
        blocks=response_blocks,
        generated_at=blocks[0].generated_at if blocks else None,
    )
