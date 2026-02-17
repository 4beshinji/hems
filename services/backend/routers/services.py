"""
Service status — in-memory store updated by Brain snapshots (Service Monitor).
"""
from fastapi import APIRouter

router = APIRouter(prefix="/services", tags=["services"])

# In-memory store: brain pushes snapshots every ~30s
_services_store: dict = {}


@router.get("/")
async def get_services_status():
    """Get latest service statuses."""
    return _services_store if _services_store else {"status": "no_data"}


@router.post("/snapshot")
async def update_services(data: dict):
    """Receive services snapshot from Brain (called every cognitive cycle)."""
    _services_store.clear()
    _services_store.update(data)
    return {"updated": True}
