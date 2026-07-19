"""Canonical biometric observation contract shared by producers and consumers."""

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hems_common.validation import validate_device_ref


class BiometricAggregation(StrEnum):
    SAMPLE = "sample"
    INTERVAL_SUM = "interval_sum"
    DAILY_TOTAL = "daily_total"
    SESSION = "session"


class BiometricMetrics(BaseModel):
    heart_rate: int | None = Field(default=None, ge=0)
    resting_heart_rate: int | None = Field(default=None, ge=0)
    spo2: int | None = Field(default=None, ge=0, le=100)
    steps: int | None = Field(default=None, ge=0)
    calories: int | None = Field(default=None, ge=0)
    active_minutes: int | None = Field(default=None, ge=0)
    stress_level: int | None = Field(default=None, ge=0)
    fatigue_score: int | None = Field(default=None, ge=0)
    sleep_duration_minutes: int | None = Field(default=None, ge=0)
    sleep_quality_score: int | None = Field(default=None, ge=0, le=100)
    hrv_ms: int | None = Field(default=None, ge=0)
    body_temperature: float | None = None
    respiratory_rate: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_metric(self):
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("metrics must contain at least one value")
        return self


class BiometricObservationIn(BaseModel):
    schema_version: Literal[1]
    observation_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    provider: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    device_id: str | None = None
    source_ts: datetime
    interval_start: datetime | None = None
    interval_end: datetime | None = None
    aggregation: BiometricAggregation
    metrics: BiometricMetrics

    model_config = ConfigDict(extra="forbid")

    @field_validator("device_id")
    @classmethod
    def validate_optional_device_id(cls, value: str | None) -> str | None:
        return validate_device_ref(value, "device_id") if value is not None else None

    @field_validator("source_ts", "interval_start", "interval_end")
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a UTC offset")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_interval(self):
        if (self.interval_start is None) != (self.interval_end is None):
            raise ValueError("interval_start and interval_end must be provided together")
        if self.interval_start is not None and self.interval_end < self.interval_start:
            raise ValueError("interval_end must not precede interval_start")
        return self


def canonical_observation_payload(data: BiometricObservationIn) -> tuple[dict, str]:
    """Return stable JSON-compatible content and its SHA-256 identity hash."""
    payload = data.model_dump(mode="json", exclude_none=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return payload, hashlib.sha256(encoded).hexdigest()


__all__ = [
    "BiometricAggregation",
    "BiometricMetrics",
    "BiometricObservationIn",
    "canonical_observation_payload",
]
