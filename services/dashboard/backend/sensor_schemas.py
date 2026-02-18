"""Pydantic response schemas for the Sensor Data API."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SensorReadingResponse(BaseModel):
    timestamp: datetime
    zone: str
    channel: str
    value: float
    device_id: str | None = None


class TimeSeriesPoint(BaseModel):
    timestamp: datetime
    avg: float
    max: float
    min: float
    count: int = 1


class TimeSeriesResponse(BaseModel):
    zone: str | None = None
    channel: str | None = None
    window: str = "1h"
    points: list[TimeSeriesPoint] = []


class ZoneSnapshotResponse(BaseModel):
    zone: str
    channels: dict[str, float] = {}
    event_count: int = 0
    last_update: datetime | None = None


class EventItemResponse(BaseModel):
    timestamp: datetime
    zone: str
    event_type: str
    source_device: str | None = None
    data: dict[str, Any] = {}


class LLMActivityResponse(BaseModel):
    cycles: int = 0
    total_tool_calls: int = 0
    avg_duration_sec: float = 0.0
    hours: int = 24
