"""Biometric latest projection and legacy reading history."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import BiometricReading
from schemas import BiometricSnapshotIn

router = APIRouter(prefix="/biometric", tags=["biometric"])
logger = logging.getLogger(__name__)


@router.get("/")
async def get_biometric(db: AsyncSession = Depends(get_db)):
    """Get latest biometric data."""
    result = await db.execute(select(BiometricReading).order_by(desc(BiometricReading.recorded_at)).limit(1))
    reading = result.scalar_one_or_none()
    if not reading:
        return {"status": "no_data"}
    return _reading_to_dict(reading)


@router.get("/history")
async def get_biometric_history(
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
):
    """Get biometric history for the given time window."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    result = await db.execute(
        select(BiometricReading).where(BiometricReading.recorded_at >= cutoff).order_by(BiometricReading.recorded_at)
    )
    readings = result.scalars().all()
    return [_reading_to_dict(r) for r in readings]


@router.post("/snapshot")
async def update_biometric(data: BiometricSnapshotIn, db: AsyncSession = Depends(get_db)):
    """Upsert the Brain's latest-state projection without creating history rows."""
    if data.uses_legacy_flat_contract():
        logger.warning("Legacy flat biometric snapshot received; migrate caller to the nested contract")

    values = data.to_flat_columns()
    result = await db.execute(select(BiometricReading).order_by(desc(BiometricReading.id)).limit(1))
    reading = result.scalar_one_or_none()
    if reading is None:
        reading = BiometricReading(**values)
        db.add(reading)
    else:
        for field, value in values.items():
            setattr(reading, field, value)
        reading.recorded_at = datetime.now(UTC)
    await db.commit()

    return {"updated": True}


def _reading_to_dict(reading: BiometricReading) -> dict:
    result = {"provider": reading.provider}
    if reading.recorded_at:
        result["recorded_at"] = reading.recorded_at.isoformat()
    for col in (
        "heart_rate",
        "resting_heart_rate",
        "spo2",
        "steps",
        "calories",
        "active_minutes",
        "stress_level",
        "fatigue_score",
        "sleep_duration_minutes",
        "sleep_quality_score",
        "hrv_ms",
        "body_temperature",
        "respiratory_rate",
    ):
        val = getattr(reading, col, None)
        if val is not None:
            result[col] = val
    return result
