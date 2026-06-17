"""
Biometric data — persisted to DB, updated by Brain snapshots (biometric-bridge integration).
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import BiometricReading

router = APIRouter(prefix="/biometric", tags=["biometric"])


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
async def update_biometric(data: dict, db: AsyncSession = Depends(get_db)):
    """Receive biometric snapshot from Brain (called every cognitive cycle)."""
    reading = BiometricReading(
        provider=data.get("provider", "unknown"),
        heart_rate=data.get("heart_rate"),
        resting_heart_rate=data.get("resting_heart_rate"),
        spo2=data.get("spo2"),
        steps=data.get("steps"),
        calories=data.get("calories"),
        active_minutes=data.get("active_minutes"),
        stress_level=data.get("stress_level"),
        fatigue_score=data.get("fatigue_score"),
        sleep_duration_minutes=data.get("sleep_duration_minutes"),
        sleep_quality_score=data.get("sleep_quality_score"),
        hrv_ms=data.get("hrv_ms"),
        body_temperature=data.get("body_temperature"),
        respiratory_rate=data.get("respiratory_rate"),
    )
    db.add(reading)
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
