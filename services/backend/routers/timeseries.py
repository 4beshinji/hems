"""
Time series data router — persistent storage for environment, biometric, and PC metrics.
Supports ingestion (Brain → Backend) and query (Frontend → Backend).
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import TimeSeriesPoint

router = APIRouter(prefix="/timeseries", tags=["timeseries"])


class TimeSeriesIngestItem(BaseModel):
    metric: str
    value: float
    zone: str | None = None
    recorded_at: str | None = None


class TimeSeriesIngestRequest(BaseModel):
    points: list[TimeSeriesIngestItem]


@router.get("/")
async def query_timeseries(
    metric: str = Query(..., description="Metric name (e.g. temperature, co2, heart_rate.bpm)"),
    zone: str | None = Query(None, description="Zone filter"),
    hours: int = Query(24, description="Lookback window in hours", ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """Query time series data for a given metric and time range."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(TimeSeriesPoint)
        .where(TimeSeriesPoint.metric == metric)
        .where(TimeSeriesPoint.recorded_at >= since)
        .order_by(TimeSeriesPoint.recorded_at.asc())
    )
    if zone:
        stmt = stmt.where(TimeSeriesPoint.zone == zone)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "value": r.value,
            "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            "zone": r.zone,
        }
        for r in rows
    ]


@router.post("/ingest")
async def ingest_timeseries(
    req: TimeSeriesIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Batch ingest time series points (Brain → Backend each cycle)."""
    for item in req.points:
        recorded = None
        if item.recorded_at:
            try:
                recorded = datetime.fromisoformat(item.recorded_at)
            except ValueError:
                pass
        point = TimeSeriesPoint(
            metric=item.metric,
            value=item.value,
            zone=item.zone,
            recorded_at=recorded or datetime.now(timezone.utc),
        )
        db.add(point)
    await db.commit()
    return {"ingested": len(req.points)}


@router.get("/metrics")
async def list_metrics(db: AsyncSession = Depends(get_db)):
    """List all available metric names."""
    stmt = select(distinct(TimeSeriesPoint.metric)).order_by(TimeSeriesPoint.metric)
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]
