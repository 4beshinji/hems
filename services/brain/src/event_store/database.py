"""
Event store database initialization — SQLite compatible (SOMS-compatible schema).
"""
import os
from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    zone TEXT,
    event_type TEXT NOT NULL,
    data TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_raw_events_ts ON raw_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_events_zone ON raw_events(zone);

CREATE TABLE IF NOT EXISTS llm_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    cycle_duration REAL,
    iterations INTEGER,
    total_tool_calls INTEGER,
    trigger_events TEXT DEFAULT '[]',
    tool_calls TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_llm_decisions_ts ON llm_decisions(timestamp);

CREATE TABLE IF NOT EXISTS hourly_aggregates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hub_id TEXT NOT NULL DEFAULT 'hems-brain',
    period_start DATETIME NOT NULL,
    zones TEXT DEFAULT '{}',
    tasks_created INTEGER DEFAULT 0,
    llm_cycles INTEGER DEFAULT 0,
    device_health TEXT DEFAULT '{}',
    UNIQUE(hub_id, period_start)
);

CREATE TABLE IF NOT EXISTS aggregation_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_aggregated_hour DATETIME,
    last_run_at DATETIME
);

INSERT OR IGNORE INTO aggregation_state (id) VALUES (1);
"""

DDL_POSTGRES = """
CREATE SCHEMA IF NOT EXISTS events;

CREATE TABLE IF NOT EXISTS events.raw_events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    zone TEXT,
    event_type TEXT NOT NULL,
    data JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_raw_events_ts ON events.raw_events USING BRIN(timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_events_zone ON events.raw_events(zone);

CREATE TABLE IF NOT EXISTS events.llm_decisions (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    cycle_duration REAL,
    iterations INTEGER,
    total_tool_calls INTEGER,
    trigger_events JSONB DEFAULT '[]',
    tool_calls JSONB DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_llm_decisions_ts ON events.llm_decisions USING BRIN(timestamp);

CREATE TABLE IF NOT EXISTS events.hourly_aggregates (
    id SERIAL PRIMARY KEY,
    hub_id TEXT NOT NULL DEFAULT 'hems-brain',
    period_start TIMESTAMPTZ NOT NULL,
    zones JSONB DEFAULT '{}',
    tasks_created INTEGER DEFAULT 0,
    llm_cycles INTEGER DEFAULT 0,
    device_health JSONB DEFAULT '{}',
    UNIQUE(hub_id, period_start)
);

CREATE TABLE IF NOT EXISTS events.aggregation_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_aggregated_hour TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ
);

INSERT INTO events.aggregation_state (id) VALUES (1) ON CONFLICT DO NOTHING;
"""


async def init_db():
    """Initialize event store database. Returns engine or None."""
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        logger.warning("No DATABASE_URL — event store disabled")
        return None

    engine = create_async_engine(db_url, echo=False)

    is_postgres = "postgresql" in db_url
    ddl = DDL_POSTGRES if is_postgres else DDL_SQLITE

    async with engine.begin() as conn:
        for statement in ddl.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(text(stmt))

    logger.info(f"Event store initialized ({'PostgreSQL' if is_postgres else 'SQLite'})")
    return engine
