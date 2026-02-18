"""Sensor Data API — read-only access to the events schema.

Endpoints surface sensor telemetry, zone overviews, event feeds,
and LLM activity summaries for the dashboard frontend.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from repositories.deps import get_sensor_repo
from repositories.sensor_repository import SensorDataRepository, TimeSeriesQuery
from sensor_schemas import (
    EventItemResponse,
    LLMActivityResponse,
    SensorReadingResponse,
    TimeSeriesPoint,
    TimeSeriesResponse,
    ZoneSnapshotResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.get("/latest", response_model=list[SensorReadingResponse])
async def get_latest_readings(
    zone: Optional[str] = Query(None, description="Filter by zone"),
    repo: SensorDataRepository = Depends(get_sensor_repo),
):
    """Latest sensor value per zone × channel (within last 10 minutes)."""
    readings = await repo.get_latest_readings(zone=zone)
    return [
        SensorReadingResponse(
            timestamp=r.timestamp,
            zone=r.zone,
            channel=r.channel,
            value=r.value,
            device_id=r.device_id,
        )
        for r in readings
    ]


@router.get("/time-series", response_model=TimeSeriesResponse)
async def get_time_series(
    zone: Optional[str] = Query(None, description="Filter by zone"),
    channel: Optional[str] = Query(None, description="Filter by channel (e.g. temperature)"),
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    window: str = Query("1h", description="Aggregation window: raw, 1h, 1d"),
    start: Optional[datetime] = Query(None, description="Start time (ISO 8601)"),
    end: Optional[datetime] = Query(None, description="End time (ISO 8601)"),
    limit: int = Query(168, ge=1, le=1000, description="Max data points"),
    repo: SensorDataRepository = Depends(get_sensor_repo),
):
    """Chart-ready time series data with configurable aggregation window."""
    query = TimeSeriesQuery(
        zone=zone,
        channel=channel,
        device_id=device_id,
        start=start,
        end=end,
        window=window,
        limit=limit,
    )
    readings = await repo.get_time_series(query)
    return TimeSeriesResponse(
        zone=zone,
        channel=channel,
        window=window,
        points=[
            TimeSeriesPoint(
                timestamp=r.period_start,
                avg=r.avg,
                max=r.max,
                min=r.min,
                count=r.count,
            )
            for r in readings
        ],
    )


@router.get("/zones", response_model=list[ZoneSnapshotResponse])
async def get_zone_overview(
    repo: SensorDataRepository = Depends(get_sensor_repo),
):
    """Overview snapshot for all zones (latest values + event count)."""
    snapshots = await repo.get_zone_overview()
    return [
        ZoneSnapshotResponse(
            zone=s.zone,
            channels=s.channels,
            event_count=s.event_count,
            last_update=s.last_update,
        )
        for s in snapshots
    ]


@router.get("/events", response_model=list[EventItemResponse])
async def get_event_feed(
    zone: Optional[str] = Query(None, description="Filter by zone"),
    limit: int = Query(50, ge=1, le=200, description="Number of events"),
    repo: SensorDataRepository = Depends(get_sensor_repo),
):
    """Recent world_model_* events (alerts, state changes)."""
    events = await repo.get_event_feed(zone=zone, limit=limit)
    return [
        EventItemResponse(
            timestamp=e.timestamp,
            zone=e.zone,
            event_type=e.event_type,
            source_device=e.source_device,
            data=e.data,
        )
        for e in events
    ]


@router.get("/llm-activity", response_model=LLMActivityResponse)
async def get_llm_activity(
    hours: int = Query(24, ge=1, le=720, description="Lookback window in hours"),
    repo: SensorDataRepository = Depends(get_sensor_repo),
):
    """LLM decision-making activity summary."""
    summary = await repo.get_llm_activity(hours=hours)
    return LLMActivityResponse(
        cycles=summary.cycles,
        total_tool_calls=summary.total_tool_calls,
        avg_duration_sec=summary.avg_duration_sec,
        hours=summary.hours,
    )
