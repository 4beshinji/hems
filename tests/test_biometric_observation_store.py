"""Focused canonical biometric observation tests without a database fixture."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from hems_common.auth import verify_internal_token
from models import BiometricObservation
from routers.biometric_internal import ingest_observation
from schemas import BiometricObservationIn


class _Result:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _Session:
    def __init__(self):
        self.row = None
        self.commit_calls = 0

    async def execute(self, _statement):
        return _Result(self.row)

    def add(self, row):
        self.row = row

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        pass


def _payload(**overrides) -> dict:
    payload = {
        "schema_version": 1,
        "observation_id": "healthconnect:hr:20260719T010203Z",
        "provider": "healthconnect",
        "device_id": "mobile.pixel_9",
        "source_ts": "2026-07-19T10:02:03+09:00",
        "interval_start": "2026-07-19T01:00:00Z",
        "interval_end": "2026-07-19T01:05:00Z",
        "aggregation": "sample",
        "metrics": {"heart_rate": 72, "spo2": 98},
    }
    payload.update(overrides)
    return payload


def test_observation_schema_normalizes_utc_and_requires_metrics():
    observation = BiometricObservationIn.model_validate(_payload())

    assert observation.source_ts == datetime(2026, 7, 19, 1, 2, 3, tzinfo=UTC)
    assert observation.metrics.heart_rate == 72

    with pytest.raises(ValidationError, match="metrics must contain at least one value"):
        BiometricObservationIn.model_validate(_payload(metrics={}))
    with pytest.raises(ValidationError, match="timestamp must include a UTC offset"):
        BiometricObservationIn.model_validate(_payload(source_ts="2026-07-19T01:02:03"))
    with pytest.raises(ValidationError, match="interval_start and interval_end"):
        BiometricObservationIn.model_validate(_payload(interval_end=None))
    with pytest.raises(ValidationError, match="observation_id"):
        BiometricObservationIn.model_validate(_payload(observation_id="invalid id"))


@pytest.mark.asyncio
async def test_internal_observation_auth_idempotency_and_conflict(monkeypatch):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "internal-secret")
    with pytest.raises(HTTPException) as unauthorized:
        verify_internal_token(None)
    assert unauthorized.value.status_code == 401
    assert verify_internal_token("Bearer internal-secret") is None

    source = (Path(__file__).resolve().parent.parent / "services" / "backend" / "main.py").read_text()
    assert "app.include_router(biometric_internal.router, dependencies=_require_internal_token)" in source

    session = _Session()
    first = await ingest_observation(BiometricObservationIn.model_validate(_payload()), session)
    duplicate = await ingest_observation(BiometricObservationIn.model_validate(_payload()), session)
    with pytest.raises(HTTPException) as conflict:
        await ingest_observation(
            BiometricObservationIn.model_validate(_payload(metrics={"heart_rate": 99})),
            session,
        )

    assert first["duplicate"] is False
    assert duplicate["duplicate"] is True
    assert conflict.value.status_code == 409
    assert session.commit_calls == 1
    assert isinstance(session.row, BiometricObservation)
    assert session.row.source_ts == datetime(2026, 7, 19, 1, 2, 3, tzinfo=UTC)
    assert session.row.interval_start == datetime(2026, 7, 19, 1, 0, tzinfo=UTC)
    assert session.row.aggregation == "sample"
    assert session.row.metrics == {"heart_rate": 72, "spo2": 98}
    assert len(session.row.payload_hash) == 64
