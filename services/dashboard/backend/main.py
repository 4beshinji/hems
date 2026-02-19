import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from database import engine, Base
from routers import tasks, users, voice_events, sensors
import models # Make sure models are registered

logger = logging.getLogger(__name__)

app = FastAPI(title="SOMS Dashboard API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _migrate_add_columns(conn):
    """Add missing columns to existing tables (stopgap until Alembic)."""
    insp = inspect(conn)

    # Collect existing columns per table
    table_columns = {}
    for table_name in insp.get_table_names():
        table_columns[table_name] = {c["name"] for c in insp.get_columns(table_name)}

    # (table, column, SQL type, default_expr_or_None)
    migrations = [
        ("tasks", "assigned_to", "INTEGER", None),
        ("tasks", "accepted_at", "TIMESTAMP WITH TIME ZONE", None),
        ("tasks", "report_status", "VARCHAR", None),
        ("tasks", "completion_note", "VARCHAR", None),
        ("users", "display_name", "VARCHAR", None),
        ("users", "is_active", "BOOLEAN", "TRUE"),
        ("users", "created_at", "TIMESTAMP WITH TIME ZONE", "NOW()"),
    ]
    for table, col_name, col_type, default in migrations:
        if table in table_columns and col_name not in table_columns[table]:
            default_clause = f" DEFAULT {default}" if default else ""
            conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}{default_clause}"
            ))
            logger.info("Migrated: added column %s.%s", table, col_name)


# Startup Event
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        # Add columns that create_all cannot add to existing tables
        await conn.run_sync(_migrate_add_columns)
        # Ensure events schema exists (owned by brain, read by sensors API)
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS events"))


# Include Routers
app.include_router(tasks.router)
app.include_router(users.router)
app.include_router(voice_events.router)
app.include_router(sensors.router)

@app.get("/")
async def root():
    return {"message": "SOMS Dashboard API Running"}
