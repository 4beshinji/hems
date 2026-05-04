"""
Weather router — in-memory store for latest snapshot from Brain.
Brain pushes weather snapshots every cognitive cycle.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/weather", tags=["weather"])

_weather_store: dict = {}


@router.get("/")
async def get_weather():
    """Return latest weather state (current/forecast/alerts) from Brain world model."""
    return _weather_store if _weather_store else {"status": "no_data"}


@router.post("/snapshot")
async def update_weather(data: dict):
    """Receive weather snapshot from Brain."""
    _weather_store.clear()
    _weather_store.update(data)
    return {"updated": True}
