"""Pure mobile observation adapters and an unwired durable persistence service."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
import schemas
from hems_common.biometric import BiometricAggregation, BiometricMetrics, BiometricObservationIn

_BIOMETRIC_METRICS = frozenset(BiometricMetrics.model_fields)


class MobileObservationConflictError(Exception):
    """A stable observation ID was reused with different canonical content."""


@dataclass(frozen=True)
class MobileDeliveryIntent:
    destination: str
    target: str
    payload: dict


@dataclass(frozen=True)
class PreparedMobileObservation:
    observation_id: str
    mobile_device_id: int
    kind: str
    observed_at: datetime
    interval_start: datetime | None
    interval_end: datetime | None
    aggregation: str | None
    canonical_payload: dict
    payload_hash: str
    deliveries: tuple[MobileDeliveryIntent, ...]


def _canonical_hash(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _legacy_time(value: datetime) -> tuple[datetime, str]:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC), "legacy_assumed_utc"
    return value.astimezone(UTC), "source_offset"


def _legacy_id(device_id: int, kind: str, canonical_section: dict) -> str:
    return f"legacy:mobile.{device_id}:{kind}:{_canonical_hash(canonical_section)}"


def _mobile_envelope(
    *,
    observation_id: str,
    device_id: int,
    kind: str,
    source_ts: datetime,
    data: dict,
    interval_start: datetime | None = None,
    interval_end: datetime | None = None,
    aggregation: str | None = None,
    batch_id: str | None = None,
    time_quality: str | None = None,
) -> dict:
    payload = {
        "schema_version": 2,
        "observation_id": observation_id,
        "device_id": f"mobile.{device_id}",
        "kind": kind,
        "source_ts": source_ts.isoformat().replace("+00:00", "Z"),
        "data": data,
    }
    if interval_start is not None:
        payload["interval_start"] = interval_start.isoformat().replace("+00:00", "Z")
        payload["interval_end"] = interval_end.isoformat().replace("+00:00", "Z")
    if aggregation is not None:
        payload["aggregation"] = aggregation
    if batch_id is not None:
        payload["batch_id"] = batch_id
    if time_quality is not None:
        payload["time_quality"] = time_quality
    return payload


def _prepare_mobile(
    *,
    observation_id: str,
    device_id: int,
    kind: str,
    source_ts: datetime,
    data: dict,
    interval_start: datetime | None = None,
    interval_end: datetime | None = None,
    aggregation: str | None = None,
    batch_id: str | None = None,
    time_quality: str | None = None,
) -> PreparedMobileObservation:
    payload = _mobile_envelope(
        observation_id=observation_id,
        device_id=device_id,
        kind=kind,
        source_ts=source_ts,
        data=data,
        interval_start=interval_start,
        interval_end=interval_end,
        aggregation=aggregation,
        batch_id=batch_id,
        time_quality=time_quality,
    )
    return PreparedMobileObservation(
        observation_id=observation_id,
        mobile_device_id=device_id,
        kind=kind,
        observed_at=source_ts,
        interval_start=interval_start,
        interval_end=interval_end,
        aggregation=aggregation,
        canonical_payload=payload,
        payload_hash=_canonical_hash(payload),
        deliveries=(
            MobileDeliveryIntent(
                destination="mqtt",
                target=f"hems/personal/mobile/mobile.{device_id}/{kind}",
                payload=payload,
            ),
        ),
    )


def _prepare_biometric(
    *,
    observation_id: str,
    device_id: int,
    metric: str,
    value: int | float,
    source_ts: datetime,
    aggregation: BiometricAggregation,
    interval_start: datetime | None = None,
    interval_end: datetime | None = None,
) -> PreparedMobileObservation:
    metrics = BiometricMetrics.model_validate({metric: value})
    biometric = BiometricObservationIn(
        schema_version=1,
        observation_id=observation_id,
        provider="mobile",
        device_id=f"mobile.{device_id}",
        source_ts=source_ts,
        interval_start=interval_start,
        interval_end=interval_end,
        aggregation=aggregation,
        metrics=metrics,
    )
    payload = biometric.model_dump(mode="json", exclude_none=True)
    return PreparedMobileObservation(
        observation_id=observation_id,
        mobile_device_id=device_id,
        kind=f"biometric.{metric}",
        observed_at=source_ts,
        interval_start=interval_start,
        interval_end=interval_end,
        aggregation=aggregation.value,
        canonical_payload=payload,
        payload_hash=_canonical_hash(payload),
        deliveries=(
            MobileDeliveryIntent(
                destination="biometric_bridge",
                target="/api/biometric/ingest",
                payload=payload,
            ),
        ),
    )


def adapt_legacy_mobile_payload(
    payload: schemas.MobileStateWebhookPayload,
    *,
    device_id: int,
) -> list[PreparedMobileObservation]:
    """Create deterministic foundation records without changing the legacy router."""
    source_ts, time_quality = _legacy_time(payload.ts)
    prepared: list[PreparedMobileObservation] = []
    sections = (
        ("location", payload.location.model_dump(exclude_none=True) if payload.location else None),
        ("activity", payload.activity.model_dump(exclude_none=True) if payload.activity else None),
        ("battery", {"percent": payload.battery_pct} if payload.battery_pct is not None else None),
    )
    for kind, data in sections:
        if data is None:
            continue
        canonical_section = {"source_ts": source_ts.isoformat(), "data": data, "time_quality": time_quality}
        observation_id = _legacy_id(device_id, kind, canonical_section)
        prepared.append(
            _prepare_mobile(
                observation_id=observation_id,
                device_id=device_id,
                kind=kind,
                source_ts=source_ts,
                data=data,
                time_quality=time_quality,
            )
        )

    if payload.biometrics:
        for metric, value in payload.biometrics.model_dump(exclude_none=True).items():
            aggregation = BiometricAggregation.SAMPLE
            interval_start = interval_end = None
            if metric == "steps":
                aggregation = BiometricAggregation.INTERVAL_SUM
                interval_start = source_ts - timedelta(minutes=20)
                interval_end = source_ts
            elif metric == "sleep_duration_minutes":
                aggregation = BiometricAggregation.LEGACY_DEGRADED
            canonical_section = {
                "source_ts": source_ts.isoformat(),
                "metric": metric,
                "value": value,
                "aggregation": aggregation.value,
                "interval_start": interval_start.isoformat() if interval_start else None,
                "interval_end": interval_end.isoformat() if interval_end else None,
            }
            observation_id = _legacy_id(device_id, metric, canonical_section)
            prepared.append(
                _prepare_biometric(
                    observation_id=observation_id,
                    device_id=device_id,
                    metric=metric,
                    value=value,
                    source_ts=source_ts,
                    aggregation=aggregation,
                    interval_start=interval_start,
                    interval_end=interval_end,
                )
            )
    return prepared


def adapt_v2_mobile_batch(
    batch: schemas.MobileStateBatchV2,
    *,
    device_id: int,
) -> list[PreparedMobileObservation]:
    prepared: list[PreparedMobileObservation] = []
    for observation in batch.observations:
        if observation.kind.startswith("biometric."):
            metric = observation.kind.removeprefix("biometric.")
            if metric not in _BIOMETRIC_METRICS:
                raise ValueError(f"unsupported biometric metric: {metric}")
            value = observation.data.get(metric, observation.data.get("value"))
            if value is None:
                raise ValueError(f"missing biometric value: {metric}")
            prepared.append(
                _prepare_biometric(
                    observation_id=observation.observation_id,
                    device_id=device_id,
                    metric=metric,
                    value=value,
                    source_ts=observation.source_ts,
                    aggregation=observation.aggregation,
                    interval_start=observation.interval_start,
                    interval_end=observation.interval_end,
                )
            )
        else:
            prepared.append(
                _prepare_mobile(
                    observation_id=observation.observation_id,
                    device_id=device_id,
                    kind=observation.kind,
                    source_ts=observation.source_ts,
                    data=observation.data,
                    interval_start=observation.interval_start,
                    interval_end=observation.interval_end,
                    aggregation=observation.aggregation.value if observation.aggregation else None,
                    batch_id=batch.batch_id,
                )
            )
    return prepared


async def persist_mobile_observation_batch(
    db: AsyncSession,
    *,
    device: models.MobileDevice,
    observations: list[PreparedMobileObservation],
) -> dict[str, int]:
    """Atomically persist inbox/outbox/device freshness; intentionally not called by the router yet."""
    inserted = duplicates = 0
    try:
        for observation in observations:
            result = await db.execute(
                select(models.MobileObservationInbox).where(
                    models.MobileObservationInbox.observation_id == observation.observation_id
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                if existing.payload_hash != observation.payload_hash:
                    raise MobileObservationConflictError(observation.observation_id)
                duplicates += 1
                continue

            db.add(
                models.MobileObservationInbox(
                    observation_id=observation.observation_id,
                    payload_hash=observation.payload_hash,
                    mobile_device_id=device.id,
                    kind=observation.kind,
                    observed_at=observation.observed_at,
                    interval_start=observation.interval_start,
                    interval_end=observation.interval_end,
                    aggregation=observation.aggregation,
                    canonical_payload=observation.canonical_payload,
                    status="pending_delivery",
                )
            )
            for delivery in observation.deliveries:
                db.add(
                    models.MobileDeliveryOutbox(
                        observation_id=observation.observation_id,
                        destination=delivery.destination,
                        target=delivery.target,
                        payload=delivery.payload,
                        status="pending",
                        attempts=0,
                    )
                )
            inserted += 1
        device.last_seen_at = datetime.now(UTC)
        await db.commit()
        return {"inserted": inserted, "duplicates": duplicates}
    except Exception:
        await db.rollback()
        raise
