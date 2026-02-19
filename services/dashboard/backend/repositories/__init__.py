"""Repository pattern for sensor data access.

Abstracts the storage backend (PostgreSQL / InfluxDB) behind a common interface.
See docs/architecture/adr-sensor-api-repository-pattern.md for design rationale.
"""
from .sensor_repository import (
    SensorDataRepository,
    SensorReading,
    AggregatedReading,
    TimeSeriesQuery,
    ZoneSnapshot,
    EventItem,
    LLMActivitySummary,
)
from .pg_sensor_repository import PgSensorRepository

__all__ = [
    "SensorDataRepository",
    "SensorReading",
    "AggregatedReading",
    "TimeSeriesQuery",
    "ZoneSnapshot",
    "EventItem",
    "LLMActivitySummary",
    "PgSensorRepository",
]
