"""
Device action log — receives transition records from Brain.
Used by frontend DeviceTimelineCard for 24h state-transition timeline.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import DeviceActionLog

router = APIRouter(prefix="/device-actions", tags=["device-actions"])


class DeviceActionEvent(BaseModel):
    device_id: str
    action: str
    params: dict | None = None
    source: str | None = None
    success: bool = True


@router.post("/")
async def record_action(event: DeviceActionEvent, db: AsyncSession = Depends(get_db)):
    """Brain pushes device control actions here for timeline / audit."""
    row = DeviceActionLog(
        device_id=event.device_id,
        action=event.action,
        params=event.params or {},
        source=event.source,
        success=event.success,
    )
    db.add(row)
    await db.commit()
    return {"ok": True, "id": row.id}


@router.get("/")
async def list_actions(
    hours: int = Query(24, ge=1, le=168),
    device_id: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Return recent device actions for timeline display."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(DeviceActionLog)
        .where(DeviceActionLog.timestamp >= since)
        .order_by(DeviceActionLog.timestamp.desc())
        .limit(limit)
    )
    if device_id:
        stmt = stmt.where(DeviceActionLog.device_id == device_id)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "actions": [
            {
                "id": r.id,
                "device_id": r.device_id,
                "action": r.action,
                "params": r.params or {},
                "source": r.source,
                "success": r.success,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ]
    }
