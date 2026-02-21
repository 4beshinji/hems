"""
Perception (camera detection) router — in-memory store for latest snapshot.
Brain pushes perception snapshots every cognitive cycle.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/perception", tags=["perception"])

_perception_store: dict = {}


@router.get("/")
async def get_perception():
    """Return latest perception data (camera occupancy/activity per zone)."""
    return _perception_store if _perception_store else {"status": "no_data"}


@router.post("/snapshot")
async def update_perception(data: dict):
    """Receive perception snapshot from Brain."""
    _perception_store.clear()
    _perception_store.update(data)
    return {"updated": True}
