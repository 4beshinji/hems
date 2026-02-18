"""Abstract base class for sensor data repositories.

Backend-agnostic interface — implementations live in pg_sensor_repository.py
(PostgreSQL) and a future influx_sensor_repository.py (InfluxDB).
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel


# ── Shared Data Models ──────────────────────────────────────────────


class TimeSeriesQuery(BaseModel):
    zone: str | None = None
    channel: str | None = None
    device_id: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    window: str = "1h"  # "raw" | "1h" | "1d"
    limit: int = 168  # 7 days hourly


class SensorReading(BaseModel):
    timestamp: datetime
    zone: str
    channel: str
    value: float
    device_id: str | None = None


class AggregatedReading(BaseModel):
    period_start: datetime
    zone: str
    channel: str
    avg: float
    max: float
    min: float
    count: int


class ZoneSnapshot(BaseModel):
    zone: str
    channels: dict[str, float]  # channel -> latest value
    event_count: int = 0
    last_update: datetime | None = None


class EventItem(BaseModel):
    timestamp: datetime
    zone: str
    event_type: str
    source_device: str | None = None
    data: dict[str, Any] = {}


class LLMActivitySummary(BaseModel):
    cycles: int = 0
    total_tool_calls: int = 0
    avg_duration_sec: float = 0.0
    hours: int = 24


# ── Abstract Repository ─────────────────────────────────────────────


class SensorDataRepository(ABC):

    @abstractmethod
    async def get_latest_readings(
        self, zone: str | None = None
    ) -> list[SensorReading]:
        """Latest value per zone × channel (within last 10 minutes)."""

    @abstractmethod
    async def get_time_series(self, query: TimeSeriesQuery) -> list[AggregatedReading]:
        """Chart-ready time series (window: raw / 1h / 1d)."""

    @abstractmethod
    async def get_zone_overview(self) -> list[ZoneSnapshot]:
        """Overview snapshot for all zones."""

    @abstractmethod
    async def get_event_feed(
        self, zone: str | None = None, limit: int = 50
    ) -> list[EventItem]:
        """Recent world_model_* events."""

    @abstractmethod
    async def get_llm_activity(self, hours: int = 24) -> LLMActivitySummary:
        """LLM decision-making summary for the given period."""
