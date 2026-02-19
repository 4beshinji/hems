"""
Knowledge status — in-memory store updated by Brain snapshots (Obsidian bridge).
"""
from fastapi import APIRouter

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# In-memory store: brain pushes snapshots every ~30s
_knowledge_store: dict = {}


@router.get("/")
async def get_knowledge_status():
    """Get latest knowledge base status."""
    return _knowledge_store if _knowledge_store else {"status": "no_data"}


@router.post("/snapshot")
async def update_knowledge(data: dict):
    """Receive knowledge snapshot from Brain (called every cognitive cycle)."""
    _knowledge_store.clear()
    _knowledge_store.update(data)
    return {"updated": True}
