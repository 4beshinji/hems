import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from auth import verify_api_key

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
    yield


app = FastAPI(
    title="HEMS Dashboard Backend",
    description="Home Environment Management System API",
    lifespan=lifespan,
)

# CORS: restrict to explicitly allowed origins.
# allow_credentials=True requires an explicit origin list (not wildcard).
_allowed_origins_raw = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8080,http://127.0.0.1:8080"
)
_allowed_origins = [o.strip() for o in _allowed_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

from routers import (
    tasks, voice_events, points, users, zones, pc, services,
    knowledge, gas, biometric, perception, home, timeseries,
)

# All routers require API key authentication.
_auth = [Depends(verify_api_key)]

app.include_router(tasks.router, dependencies=_auth)
app.include_router(voice_events.router, dependencies=_auth)
app.include_router(points.router, dependencies=_auth)
app.include_router(users.router, dependencies=_auth)
app.include_router(zones.router, dependencies=_auth)
app.include_router(pc.router, dependencies=_auth)
app.include_router(services.router, dependencies=_auth)
app.include_router(knowledge.router, dependencies=_auth)
app.include_router(gas.router, dependencies=_auth)
app.include_router(biometric.router, dependencies=_auth)
app.include_router(perception.router, dependencies=_auth)
app.include_router(home.router, dependencies=_auth)
app.include_router(timeseries.router, dependencies=_auth)


@app.get("/")
async def root():
    return {"service": "HEMS Backend", "status": "running"}


@app.get("/health")
async def health():
    """Health check endpoint — no auth required for Docker healthcheck."""
    return {"status": "ok"}
