"""
Zone sensor data — in-memory store updated by Brain snapshots.
"""
from fastapi import APIRouter
from schemas import ZonesUpdate, ZoneSnapshot

router = APIRouter(prefix="/zones", tags=["zones"])

# In-memory store: brain pushes snapshots every ~30s
_zone_store: dict[str, ZoneSnapshot] = {}


@router.get("/", response_model=list[ZoneSnapshot])
async def get_zones():
    """Get latest zone sensor data."""
    return list(_zone_store.values())


@router.post("/snapshot")
async def update_zones(data: ZonesUpdate):
    """Receive zone snapshot from Brain (called every cognitive cycle)."""
    for zone in data.zones:
        _zone_store[zone.zone_id] = zone
    return {"updated": len(data.zones)}
