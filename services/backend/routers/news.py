"""
News router — in-memory store for latest snapshot from Brain.
Brain pushes news state every cognitive cycle.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/news", tags=["news"])

_news_store: dict = {}


@router.get("/")
async def get_news():
    """Return latest news state (daily summary chunks + urgent articles)."""
    return _news_store if _news_store else {"status": "no_data"}


@router.post("/snapshot")
async def update_news(data: dict):
    """Receive news snapshot from Brain."""
    _news_store.clear()
    _news_store.update(data)
    return {"updated": True}
