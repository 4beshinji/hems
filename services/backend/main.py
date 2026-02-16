import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers import tasks, voice_events, points, users

app.include_router(tasks.router)
app.include_router(voice_events.router)
app.include_router(points.router)
app.include_router(users.router)


@app.get("/")
async def root():
    return {"service": "HEMS Backend", "status": "running"}
