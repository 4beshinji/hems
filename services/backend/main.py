import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth import verify_api_key
from database import Base, engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data directory exists for SQLite
    db_url = os.getenv("DATABASE_URL", "")
    if "sqlite" in db_url:
        db_path = db_url.split("///")[-1] if "///" in db_url else "./data/hems.db"
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")

    # Lightweight column migration for existing SQLite DBs
    from sqlalchemy import text

    async with engine.begin() as conn:
        for col in ["motion_id"]:
            try:
                await conn.execute(text(f"ALTER TABLE voice_events ADD COLUMN {col} VARCHAR"))
                logger.info(f"Added {col} column to voice_events")
            except Exception:
                pass

        timeline_task_cols = [
            ("cognitive_load", "INTEGER"),
            ("preferred_time_slot", "VARCHAR"),
            ("deadline", "DATETIME"),
            ("source", "VARCHAR"),
            ("source_ref", "VARCHAR"),
            ("confidence", "REAL"),
            ("proposal_status", "VARCHAR"),
            ("dismissed_at", "DATETIME"),
            ("dismiss_reason", "VARCHAR"),
            ("locked_start", "DATETIME"),
        ]
        for col, col_type in timeline_task_cols:
            try:
                await conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}"))
                logger.info(f"Added {col} column to tasks")
            except Exception:
                pass

        shopping_item_cols = [
            ("store_category", "VARCHAR"),
        ]
        for col, col_type in shopping_item_cols:
            try:
                await conn.execute(text(f"ALTER TABLE shopping_items ADD COLUMN {col} {col_type}"))
                logger.info(f"Added {col} column to shopping_items")
            except Exception:
                pass

        device_cols = [
            ("model_id", "VARCHAR"),
            ("manufacturer", "VARCHAR"),
            ("link_quality", "INTEGER"),
            ("last_seen_reported", "DATETIME"),
        ]
        for col, col_type in device_cols:
            try:
                await conn.execute(text(f"ALTER TABLE devices ADD COLUMN {col} {col_type}"))
                logger.info(f"Added {col} column to devices")
            except Exception:
                pass
    yield


app = FastAPI(
    title="HEMS Dashboard Backend",
    description="Home Environment Management System API",
    lifespan=lifespan,
)

# CORS: restrict to explicitly allowed origins.
# allow_credentials=True requires an explicit origin list (not wildcard).
_allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080")
_allowed_origins = [o.strip() for o in _allowed_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

from routers import (
    automations,
    biometric,
    brain,
    bridge_status,
    character,
    chat,
    classifier_cache,
    device_actions,
    devices,
    frequent_places,
    gas,
    home,
    knowledge,
    mobile,
    news,
    pc,
    perception,
    scenes,
    services,
    shopping,
    tasks,
    timeline,
    timeseries,
    users,
    voice_events,
    weather,
    zones,
)

# All routers require API key authentication.
_auth = [Depends(verify_api_key)]

app.include_router(tasks.router, dependencies=_auth)
app.include_router(voice_events.router, dependencies=_auth)
app.include_router(users.router, dependencies=_auth)
app.include_router(zones.router, dependencies=_auth)
app.include_router(weather.router, dependencies=_auth)
app.include_router(news.router, dependencies=_auth)
app.include_router(bridge_status.router, dependencies=_auth)
app.include_router(device_actions.router, dependencies=_auth)
app.include_router(pc.router, dependencies=_auth)
app.include_router(services.router, dependencies=_auth)
app.include_router(knowledge.router, dependencies=_auth)
app.include_router(gas.router, dependencies=_auth)
app.include_router(biometric.router, dependencies=_auth)
app.include_router(perception.router, dependencies=_auth)
app.include_router(home.router, dependencies=_auth)
app.include_router(timeseries.router, dependencies=_auth)
app.include_router(character.router, dependencies=_auth)
app.include_router(shopping.router, dependencies=_auth)
app.include_router(chat.router, dependencies=_auth)
app.include_router(timeline.router, dependencies=_auth)
app.include_router(brain.router, dependencies=_auth)
app.include_router(devices.router, dependencies=_auth)
app.include_router(scenes.router, dependencies=_auth)
app.include_router(automations.router, dependencies=_auth)
app.include_router(frequent_places.router, dependencies=_auth)
app.include_router(classifier_cache.router, dependencies=_auth)
# Mobile admin routes apply verify_api_key themselves; device routes authenticate per-endpoint.
app.include_router(mobile.admin_router)
app.include_router(mobile.device_router)


@app.get("/")
async def root():
    return {"service": "HEMS Backend", "status": "running"}


@app.get("/health")
async def health():
    """Health check endpoint — no auth required for Docker healthcheck."""
    return {"status": "ok"}
