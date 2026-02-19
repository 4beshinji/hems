"""FastAPI dependency injection for sensor data repository.

Swap the implementation here to switch storage backends (PG → InfluxDB).
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from .pg_sensor_repository import PgSensorRepository
from .sensor_repository import SensorDataRepository


async def get_sensor_repo(
    session: AsyncSession = Depends(get_db),
) -> SensorDataRepository:
    return PgSensorRepository(session)
