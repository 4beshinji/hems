"""
GAS status — in-memory store updated by Brain snapshots (GAS bridge).
"""
from fastapi import APIRouter

router = APIRouter(prefix="/gas", tags=["gas"])

# In-memory store: brain pushes snapshots every ~30s
_gas_store: dict = {}


@router.get("/")
async def get_gas_status():
    """Get latest GAS integration status."""
    return _gas_store if _gas_store else {"status": "no_data"}


@router.post("/snapshot")
async def update_gas(data: dict):
    """Receive GAS snapshot from Brain (called every cognitive cycle)."""
    _gas_store.clear()
    _gas_store.update(data)
    return {"updated": True}
