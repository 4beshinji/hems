import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete

from auth import verify_api_key
from database import AsyncSessionLocal, Base, engine
from models import BiometricReading, PurchaseHistory, Task, TimeSeriesPoint, VoiceEvent

logger = logging.getLogger(__name__)


async def _add_column_if_missing(conn, table: str, col: str, col_type: str) -> None:
    """Best-effort additive column migration for existing SQLite/Postgres DBs.

    This is a hand-rolled migration, NOT a framework. It only adds columns; it
    cannot drop/rename/alter types or order changes. The "column already exists"
    case (re-run on an up-to-date DB) is expected and logged at debug; any other
    DDL failure is surfaced as a warning instead of being silently swallowed.
    A proper migration tool (Alembic) is the intended follow-up and is out of
    scope here.
    """
    from sqlalchemy import text

    try:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
        logger.info(f"Added {col} column to {table}")
    except Exception as e:
        msg = str(e).lower()
        if "duplicate column" in msg or "already exists" in msg:
            logger.debug(f"Column {table}.{col} already present; skipping")
        else:
            logger.warning(f"Column migration {table}.{col} failed: {e}")


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

    # Lightweight additive column migration for existing SQLite/Postgres DBs.
    # (Hand-rolled; see _add_column_if_missing. Alembic is the intended follow-up.)
    migrations: list[tuple[str, str, str]] = [
        ("voice_events", "motion_id", "VARCHAR"),
        ("tasks", "cognitive_load", "INTEGER"),
        ("tasks", "preferred_time_slot", "VARCHAR"),
        ("tasks", "deadline", "DATETIME"),
        ("tasks", "source", "VARCHAR"),
        ("tasks", "source_ref", "VARCHAR"),
        ("tasks", "confidence", "REAL"),
        ("tasks", "proposal_status", "VARCHAR"),
        ("tasks", "dismissed_at", "DATETIME"),
        ("tasks", "dismiss_reason", "VARCHAR"),
        ("tasks", "locked_start", "DATETIME"),
        ("shopping_items", "store_category", "VARCHAR"),
        ("devices", "model_id", "VARCHAR"),
        ("devices", "manufacturer", "VARCHAR"),
        ("devices", "link_quality", "INTEGER"),
        ("devices", "last_seen_reported", "DATETIME"),
    ]
    for table, col, col_type in migrations:
        # Per-column transaction so one failure can't abort the rest (Postgres
        # aborts the whole tx on a failed statement).
        async with engine.begin() as conn:
            await _add_column_if_missing(conn, table, col, col_type)

    # W1.2: Audit existing Device rows for identifier safety.
    # Rows that pre-date validation are left intact (no deletion/rejection) but
    # a warning is emitted so operators can review and manually correct them.
    await _audit_existing_device_ids()

    # Background retention cleanup for tables without natural deletion.
    cleanup_task = asyncio.create_task(_retention_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


# Retention policies: (model, datetime_column, days_to_keep)
RETENTION_POLICIES: list[tuple[type, str, int]] = [
    (TimeSeriesPoint, "recorded_at", 30),
    (VoiceEvent, "created_at", 90),
    (BiometricReading, "recorded_at", 90),
    (PurchaseHistory, "purchased_at", 365),
]

# Task retention: only completed tasks older than N days.
TASK_RETENTION_DAYS = 365


async def _run_retention_cleanup(session) -> dict[str, int]:
    """Delete old records according to RETENTION_POLICIES.

    Returns a mapping of table name -> deleted row count.
    """
    cutoff_base = datetime.now(UTC) - timedelta(days=1)
    deleted: dict[str, int] = {}

    for model, col_name, days in RETENTION_POLICIES:
        cutoff = cutoff_base - timedelta(days=days - 1)
        col = getattr(model, col_name)
        result = await session.execute(delete(model).where(col < cutoff))
        deleted[model.__tablename__] = result.rowcount
        if result.rowcount:
            logger.info(
                "Retention cleanup: deleted %d row(s) from %s older than %s",
                result.rowcount,
                model.__tablename__,
                cutoff.isoformat(),
            )

    # Completed tasks
    task_cutoff = cutoff_base - timedelta(days=TASK_RETENTION_DAYS - 1)
    result = await session.execute(
        delete(Task).where(
            Task.is_completed.is_(True),
            Task.completed_at < task_cutoff,
        )
    )
    deleted[Task.__tablename__] = result.rowcount
    if result.rowcount:
        logger.info(
            "Retention cleanup: deleted %d completed task(s) older than %s",
            result.rowcount,
            task_cutoff.isoformat(),
        )

    return deleted


async def _retention_cleanup_loop() -> None:
    """Periodically delete old records according to RETENTION_POLICIES."""
    while True:
        try:
            await asyncio.sleep(3600)  # run once per hour
            async with AsyncSessionLocal() as session:
                await _run_retention_cleanup(session)
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Retention cleanup loop iteration failed: %s", exc)


async def _audit_existing_device_ids() -> None:
    """Scan Device table for rows whose device_id or vendor_ref violate the
    unified identifier rules introduced in W1.2/W1.8.

    Existing rows are NOT modified — this is a read-only audit that logs
    warnings so operators can clean up legacy data at their own pace.
    """
    from sqlalchemy.future import select

    import models
    from database import AsyncSessionLocal
    from hems_common.validation import is_valid_device_ref

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(models.Device))
            devices = result.scalars().all()
        bad: list[str] = []
        for d in devices:
            if not is_valid_device_ref(d.device_id):
                bad.append(f"device_id={d.device_id!r} (id={d.id})")
            if not is_valid_device_ref(d.vendor_ref):
                bad.append(f"vendor_ref={d.vendor_ref!r} for device_id={d.device_id!r} (id={d.id})")
        if bad:
            logger.warning(
                "W1.8 audit: %d existing Device row(s) contain unsafe identifier(s) — "
                "these are NOT rejected but should be reviewed: %s",
                len(bad),
                "; ".join(bad),
            )
        else:
            logger.info("W1.8 audit: all existing Device identifiers pass the safe-character check")
    except Exception as exc:
        logger.warning("W1.8 audit: could not scan Device table: %s", exc)


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

# All dashboard routers gate on the shared key (enforced only when
# BACKEND_API_KEY is set; open for zero-config LAN use otherwise).
_require_api_key = [Depends(verify_api_key)]

app.include_router(tasks.router, dependencies=_require_api_key)
app.include_router(voice_events.router, dependencies=_require_api_key)
app.include_router(users.router, dependencies=_require_api_key)
app.include_router(zones.router, dependencies=_require_api_key)
app.include_router(weather.router, dependencies=_require_api_key)
app.include_router(news.router, dependencies=_require_api_key)
app.include_router(bridge_status.router, dependencies=_require_api_key)
app.include_router(device_actions.router, dependencies=_require_api_key)
app.include_router(pc.router, dependencies=_require_api_key)
app.include_router(services.router, dependencies=_require_api_key)
app.include_router(knowledge.router, dependencies=_require_api_key)
app.include_router(gas.router, dependencies=_require_api_key)
app.include_router(biometric.router, dependencies=_require_api_key)
app.include_router(perception.router, dependencies=_require_api_key)
app.include_router(home.router, dependencies=_require_api_key)
app.include_router(timeseries.router, dependencies=_require_api_key)
app.include_router(character.router, dependencies=_require_api_key)
app.include_router(shopping.router, dependencies=_require_api_key)
app.include_router(chat.router, dependencies=_require_api_key)
app.include_router(timeline.router, dependencies=_require_api_key)
app.include_router(brain.router, dependencies=_require_api_key)
app.include_router(devices.router, dependencies=_require_api_key)
app.include_router(scenes.router, dependencies=_require_api_key)
app.include_router(automations.router, dependencies=_require_api_key)
app.include_router(frequent_places.router, dependencies=_require_api_key)
app.include_router(classifier_cache.router, dependencies=_require_api_key)
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
