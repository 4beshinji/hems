"""Focused P1.3a mobile observation adapter and transaction tests."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import models
import schemas
from mobile_observations import (
    MobileObservationConflictError,
    adapt_legacy_mobile_payload,
    adapt_v2_mobile_batch,
    persist_mobile_observation_batch,
)

_ROOT = Path(__file__).resolve().parent.parent


class _Result:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _Session:
    def __init__(self, existing=(), commit_error=None):
        self.existing = list(existing)
        self.commit_error = commit_error
        self.added = []
        self.commit_calls = 0
        self.rollback_calls = 0

    async def execute(self, _statement):
        return _Result(self.existing.pop(0) if self.existing else None)

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.commit_calls += 1
        if self.commit_error:
            raise self.commit_error

    async def rollback(self):
        self.rollback_calls += 1


def _legacy_payload(ts="2026-07-19T12:00:00+09:00"):
    return schemas.MobileStateWebhookPayload.model_validate(
        {
            "ts": ts,
            "location": {"lat": 35.0, "lon": 139.0, "accuracy_m": 5},
            "activity": {"kind": "walking", "confidence": 90},
            "battery_pct": 81,
            "biometrics": {
                "heart_rate": 72,
                "spo2": 98,
                "steps": 1200,
                "stress_level": 20,
                "sleep_duration_minutes": 410,
            },
        }
    )


def test_legacy_adapter_is_deterministic_and_emits_every_delivery_intent():
    first = adapt_legacy_mobile_payload(_legacy_payload(), device_id=7)
    second = adapt_legacy_mobile_payload(_legacy_payload(), device_id=7)

    assert len(first) == 8
    assert [item.observation_id for item in first] == [item.observation_id for item in second]
    assert len({item.observation_id for item in first}) == 8
    assert all(item.observation_id.startswith("legacy:mobile.7:") for item in first)

    mobile = {item.kind: item for item in first if not item.kind.startswith("biometric.")}
    assert mobile["location"].deliveries[0].target == "hems/personal/mobile/mobile.7/location"
    assert mobile["activity"].deliveries[0].target == "hems/personal/mobile/mobile.7/activity"
    assert mobile["battery"].deliveries[0].payload["data"] == {"percent": 81}

    biometric = {item.kind: item for item in first if item.kind.startswith("biometric.")}
    assert all(item.deliveries[0].target == "/api/biometric/ingest" for item in biometric.values())
    assert biometric["biometric.heart_rate"].aggregation == "sample"
    assert biometric["biometric.heart_rate"].interval_start is None
    steps = biometric["biometric.steps"]
    assert steps.aggregation == "interval_sum"
    assert (steps.interval_end - steps.interval_start).total_seconds() == 20 * 60
    sleep = biometric["biometric.sleep_duration_minutes"]
    assert sleep.aggregation == "legacy_degraded"
    assert sleep.interval_start is None  # never infer a session window from one duration scalar


def test_foundation_is_not_wired_into_legacy_mobile_router():
    source = (_ROOT / "services" / "backend" / "routers" / "mobile.py").read_text()
    assert "persist_mobile_observation_batch" not in source
    assert "adapt_legacy_mobile_payload" not in source


def test_legacy_naive_time_is_explicitly_degraded_to_assumed_utc():
    location = adapt_legacy_mobile_payload(
        schemas.MobileStateWebhookPayload.model_validate(
            {"ts": "2026-07-19T03:00:00", "location": {"lat": 35.0, "lon": 139.0}}
        ),
        device_id=2,
    )[0]

    assert location.observed_at == datetime(2026, 7, 19, 3, tzinfo=UTC)
    assert location.canonical_payload["time_quality"] == "legacy_assumed_utc"


def test_v2_adapter_preserves_record_ids_utc_times_and_intervals():
    batch = schemas.MobileStateBatchV2.model_validate(
        {
            "schema_version": 2,
            "batch_id": "batch:phone:42",
            "observations": [
                {
                    "observation_id": "record:location:1",
                    "kind": "location",
                    "source_ts": "2026-07-19T12:00:00+09:00",
                    "data": {"lat": 35.0, "lon": 139.0},
                },
                {
                    "observation_id": "record:steps:1",
                    "kind": "biometric.steps",
                    "source_ts": "2026-07-19T03:20:00Z",
                    "interval_start": "2026-07-19T03:00:00Z",
                    "interval_end": "2026-07-19T03:20:00Z",
                    "aggregation": "interval_sum",
                    "data": {"steps": 500},
                },
            ],
        }
    )
    prepared = adapt_v2_mobile_batch(batch, device_id=42)

    assert [item.observation_id for item in prepared] == ["record:location:1", "record:steps:1"]
    assert prepared[0].observed_at == datetime(2026, 7, 19, 3, tzinfo=UTC)
    assert prepared[0].canonical_payload["batch_id"] == "batch:phone:42"
    assert prepared[1].interval_start == datetime(2026, 7, 19, 3, tzinfo=UTC)
    assert prepared[1].canonical_payload["metrics"] == {"steps": 500}


def test_v2_schema_rejects_naive_time_duplicate_ids_and_missing_biometric_aggregation():
    base = {
        "schema_version": 2,
        "batch_id": "batch:1",
        "observations": [
            {
                "observation_id": "record:1",
                "kind": "location",
                "source_ts": "2026-07-19T03:00:00",
                "data": {"lat": 35.0},
            }
        ],
    }
    with pytest.raises(ValidationError, match="UTC offset"):
        schemas.MobileStateBatchV2.model_validate(base)

    duplicate = {**base, "observations": [{**base["observations"][0], "source_ts": "2026-07-19T03:00:00Z"}] * 2}
    with pytest.raises(ValidationError, match="unique"):
        schemas.MobileStateBatchV2.model_validate(duplicate)

    biometric = {
        **base,
        "observations": [
            {
                "observation_id": "record:hr:1",
                "kind": "biometric.heart_rate",
                "source_ts": "2026-07-19T03:00:00Z",
                "data": {"heart_rate": 70},
            }
        ],
    }
    with pytest.raises(ValidationError, match="require aggregation"):
        schemas.MobileStateBatchV2.model_validate(biometric)


@pytest.mark.asyncio
async def test_persistence_adds_all_inbox_outbox_rows_and_device_freshness():
    observations = adapt_legacy_mobile_payload(_legacy_payload(), device_id=7)
    session = _Session()
    device = SimpleNamespace(id=7, last_seen_at=None)

    result = await persist_mobile_observation_batch(session, device=device, observations=observations)

    assert result == {"inserted": 8, "duplicates": 0}
    assert session.commit_calls == 1
    assert session.rollback_calls == 0
    assert len([row for row in session.added if isinstance(row, models.MobileObservationInbox)]) == 8
    deliveries = [row for row in session.added if isinstance(row, models.MobileDeliveryOutbox)]
    assert len(deliveries) == 8
    assert {row.destination for row in deliveries} == {"mqtt", "biometric_bridge"}
    assert device.last_seen_at is not None


@pytest.mark.asyncio
async def test_persistence_idempotency_conflict_and_rollback():
    observation = adapt_legacy_mobile_payload(_legacy_payload(), device_id=7)[0]
    device = SimpleNamespace(id=7, last_seen_at=None)

    duplicate_session = _Session(existing=[SimpleNamespace(payload_hash=observation.payload_hash)])
    result = await persist_mobile_observation_batch(
        duplicate_session,
        device=device,
        observations=[observation],
    )
    assert result == {"inserted": 0, "duplicates": 1}
    assert duplicate_session.added == []

    conflict_session = _Session(existing=[SimpleNamespace(payload_hash="different")])
    with pytest.raises(MobileObservationConflictError):
        await persist_mobile_observation_batch(conflict_session, device=device, observations=[observation])
    assert conflict_session.commit_calls == 0
    assert conflict_session.rollback_calls == 1

    failed_session = _Session(commit_error=RuntimeError("forced commit failure"))
    with pytest.raises(RuntimeError, match="forced commit failure"):
        await persist_mobile_observation_batch(failed_session, device=device, observations=[observation])
    assert failed_session.rollback_calls == 1
