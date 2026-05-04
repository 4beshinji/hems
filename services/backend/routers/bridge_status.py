"""
Bridge status SLA logging — receives state transitions from Brain and exposes uptime stats.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import BridgeStatusLog

router = APIRouter(prefix="/bridge-status", tags=["bridge-status"])


class BridgeStatusEvent(BaseModel):
    service: str
    state: str  # "connected" | "disconnected"
    detail: str | None = None


@router.post("/event")
async def record_event(event: BridgeStatusEvent, db: AsyncSession = Depends(get_db)):
    """Brain pushes bridge state transitions here for outage history."""
    if event.state not in ("connected", "disconnected"):
        raise HTTPException(status_code=400, detail="state must be 'connected' or 'disconnected'")

    row = BridgeStatusLog(service=event.service, state=event.state, detail=event.detail)
    db.add(row)
    await db.commit()
    return {"ok": True, "id": row.id}


@router.get("/uptime")
async def uptime(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Per-service uptime % over the last N days, plus disconnect counts."""
    days = max(1, min(days, 30))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(BridgeStatusLog.service, BridgeStatusLog.state, func.count())
        .where(BridgeStatusLog.timestamp >= since)
        .group_by(BridgeStatusLog.service, BridgeStatusLog.state)
    )
    rows = result.all()

    services: dict[str, dict[str, int]] = {}
    for service, state, count in rows:
        services.setdefault(service, {"connected": 0, "disconnected": 0})[state] = count

    return {
        "window_days": days,
        "since": since.isoformat(),
        "services": [
            {
                "service": svc,
                "disconnect_count": counts.get("disconnected", 0),
                "connect_count": counts.get("connected", 0),
            }
            for svc, counts in sorted(services.items())
        ],
    }


@router.get("/recent")
async def recent_events(limit: int = 50, service: str | None = None, db: AsyncSession = Depends(get_db)):
    """Return the most recent state transition events."""
    limit = max(1, min(limit, 500))
    stmt = select(BridgeStatusLog).order_by(BridgeStatusLog.timestamp.desc()).limit(limit)
    if service:
        stmt = stmt.where(BridgeStatusLog.service == service)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "events": [
            {
                "id": r.id,
                "service": r.service,
                "state": r.state,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "detail": r.detail,
            }
            for r in rows
        ]
    }
