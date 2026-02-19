"""
PC metrics — in-memory store updated by Brain snapshots (OpenClaw integration).
"""
from fastapi import APIRouter

router = APIRouter(prefix="/pc", tags=["pc"])

# In-memory store: brain pushes snapshots every ~30s
_pc_store: dict = {}


@router.get("/")
async def get_pc_status():
    """Get latest PC metrics."""
    return _pc_store if _pc_store else {"status": "no_data"}


@router.post("/snapshot")
async def update_pc(data: dict):
    """Receive PC snapshot from Brain (called every cognitive cycle)."""
    _pc_store.clear()
    _pc_store.update(data)
    return {"updated": True}
