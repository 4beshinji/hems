"""Internal canonical biometric observation ingest."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from hems_common.biometric import BiometricObservationIn, canonical_observation_payload
from models import BiometricObservation

router = APIRouter(prefix="/internal/biometric", tags=["biometric-internal"])


def _duplicate_response(observation_id: str) -> dict:
    return {"accepted": True, "duplicate": True, "observation_id": observation_id}


@router.post("/observations")
async def ingest_observation(data: BiometricObservationIn, db: AsyncSession = Depends(get_db)):
    """Persist one immutable observation, idempotently by observation_id."""
    payload, payload_hash = canonical_observation_payload(data)
    existing = await _get_observation(db, data.observation_id)
    if existing is not None:
        if existing.payload_hash == payload_hash:
            return _duplicate_response(data.observation_id)
        raise HTTPException(status_code=409, detail="observation_id already exists with different payload")

    row = BiometricObservation(
        schema_version=data.schema_version,
        observation_id=data.observation_id,
        payload_hash=payload_hash,
        provider=data.provider,
        device_id=data.device_id,
        source_ts=data.source_ts,
        interval_start=data.interval_start,
        interval_end=data.interval_end,
        aggregation=data.aggregation.value,
        metrics=payload["metrics"],
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_observation(db, data.observation_id)
        if existing is not None and existing.payload_hash == payload_hash:
            return _duplicate_response(data.observation_id)
        raise HTTPException(status_code=409, detail="observation_id already exists with different payload") from None

    return {"accepted": True, "duplicate": False, "observation_id": data.observation_id}


async def _get_observation(db: AsyncSession, observation_id: str) -> BiometricObservation | None:
    result = await db.execute(select(BiometricObservation).where(BiometricObservation.observation_id == observation_id))
    return result.scalar_one_or_none()
