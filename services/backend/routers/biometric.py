"""
Biometric data — in-memory store updated by Brain snapshots (biometric-bridge integration).
"""
from fastapi import APIRouter

router = APIRouter(prefix="/biometric", tags=["biometric"])

# In-memory store: brain pushes snapshots every ~30s
_bio_store: dict = {}


@router.get("/")
async def get_biometric():
    """Get latest biometric data."""
    return _bio_store if _bio_store else {"status": "no_data"}


@router.post("/snapshot")
async def update_biometric(data: dict):
    """Receive biometric snapshot from Brain (called every cognitive cycle)."""
    _bio_store.clear()
    _bio_store.update(data)
    return {"updated": True}
