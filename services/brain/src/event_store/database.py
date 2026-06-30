"""
Event store database initialization — SQLite compatible (SOMS-compatible schema).

Uses raw SQL DDL (no Alembic) — Phase 0 simplicity.
Tables are created with IF NOT EXISTS for idempotent startup.
"""

import os

from loguru import logger
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_engine: AsyncEngine | None = None

DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    zone TEXT,
    event_type TEXT NOT NULL,
    source_device TEXT,
    data TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_raw_events_ts ON raw_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_events_zone ON raw_events(zone);
CREATE INDEX IF NOT EXISTS idx_raw_events_zone_type ON raw_events(zone, event_type);

CREATE TABLE IF NOT EXISTS llm_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    cycle_duration_sec REAL,
    iterations INTEGER,
    total_tool_calls INTEGER,
    trigger_events TEXT DEFAULT '[]',
    tool_calls TEXT DEFAULT '[]',
    world_state_snapshot TEXT DEFAULT '{}',
    cause_event_id INTEGER REFERENCES world_events(id),
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    gpu_util_pct REAL,
    gpu_power_w REAL
);

CREATE INDEX IF NOT EXISTS idx_llm_decisions_ts ON llm_decisions(timestamp);
-- idx_llm_decisions_cause is created in the migration block below, after the
-- cause_event_id column is guaranteed to exist (pre-cause_event_id DBs would
-- otherwise fail "no such column" here, aborting event-store init).

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

CREATE TABLE IF NOT EXISTS world_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    source_type TEXT NOT NULL,
    topic TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    subject_ref TEXT,
    data TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_world_events_ts ON world_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_world_events_source ON world_events(source_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_world_events_digest ON world_events(payload_digest, timestamp);

-- Self-contained intervention efficacy loop (Group D). Each row tracks one
-- environment task: baseline metric at creation, post-completion metric, verdict.
-- Phase 0 HITL extension: ties efficacy measurement to approval decisions and rollback.
CREATE TABLE IF NOT EXISTS intervention_efficacy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    zone TEXT NOT NULL,
    trigger_metric TEXT NOT NULL,
    baseline_value REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    post_value REAL,
    window_sec INTEGER NOT NULL DEFAULT 1800,
    verdict TEXT,
    evaluated_at DATETIME,
    approval_id TEXT,
    human_decision TEXT,
    rolled_back INTEGER DEFAULT 0,
    rollback_success INTEGER,
    efficacy_score REAL
);

CREATE INDEX IF NOT EXISTS idx_intervention_efficacy_pending ON intervention_efficacy(completed_at);
CREATE INDEX IF NOT EXISTS idx_intervention_efficacy_zone ON intervention_efficacy(zone);

-- Phase 1 feedback / learning tables
CREATE TABLE IF NOT EXISTS agent_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'frontend',
    payload TEXT DEFAULT '{}',
    context TEXT DEFAULT '{}',
    user_id TEXT,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_feedback_target ON agent_feedback(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_agent_feedback_type ON agent_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_agent_feedback_recorded_at ON agent_feedback(recorded_at);

CREATE TABLE IF NOT EXISTS agent_trajectories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT,
    decision_id TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    trigger_events TEXT DEFAULT '[]',
    tool_calls TEXT DEFAULT '[]',
    world_state_snapshot TEXT DEFAULT '{}',
    outcome_summary TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_agent_trajectories_cycle ON agent_trajectories(cycle_id);
CREATE INDEX IF NOT EXISTS idx_agent_trajectories_timestamp ON agent_trajectories(timestamp);
"""

DDL_POSTGRES = """
CREATE SCHEMA IF NOT EXISTS events;

CREATE TABLE IF NOT EXISTS events.raw_events (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    zone TEXT,
    event_type TEXT NOT NULL,
    source_device TEXT,
    data JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_raw_events_ts ON events.raw_events USING BRIN(timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_events_zone ON events.raw_events(zone);
CREATE INDEX IF NOT EXISTS idx_raw_events_zone_type ON events.raw_events(zone, event_type);

CREATE TABLE IF NOT EXISTS events.llm_decisions (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cycle_duration_sec REAL NOT NULL,
    iterations INTEGER NOT NULL,
    total_tool_calls INTEGER NOT NULL,
    trigger_events JSONB NOT NULL DEFAULT '[]',
    tool_calls JSONB NOT NULL DEFAULT '[]',
    world_state_snapshot JSONB NOT NULL DEFAULT '{}',
    cause_event_id BIGINT REFERENCES events.world_events(id),
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    gpu_util_pct REAL,
    gpu_power_w REAL
);

CREATE INDEX IF NOT EXISTS idx_llm_decisions_ts ON events.llm_decisions USING BRIN(timestamp);
-- idx_llm_decisions_cause is created in the migration block below, after the
-- cause_event_id column is ensured (pre-cause_event_id tables would otherwise
-- fail "column does not exist" here, aborting event-store init).

CREATE TABLE IF NOT EXISTS events.hourly_aggregates (
    id SERIAL PRIMARY KEY,
    hub_id TEXT NOT NULL DEFAULT 'hems-brain',
    period_start TIMESTAMPTZ NOT NULL,
    zones JSONB NOT NULL DEFAULT '{}',
    tasks_created INTEGER NOT NULL DEFAULT 0,
    llm_cycles INTEGER NOT NULL DEFAULT 0,
    device_health JSONB NOT NULL DEFAULT '{}',
    UNIQUE(hub_id, period_start)
);

CREATE TABLE IF NOT EXISTS events.aggregation_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_aggregated_hour TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ
);

INSERT INTO events.aggregation_state (id) VALUES (1) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS events.world_events (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_type TEXT NOT NULL,
    topic TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    subject_ref TEXT,
    data JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_world_events_ts ON events.world_events USING BRIN(timestamp);
CREATE INDEX IF NOT EXISTS idx_world_events_source ON events.world_events(source_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_world_events_digest ON events.world_events(payload_digest, timestamp);

CREATE TABLE IF NOT EXISTS events.intervention_efficacy (
    id              BIGSERIAL PRIMARY KEY,
    task_id         TEXT NOT NULL,
    zone            TEXT NOT NULL,
    trigger_metric  TEXT NOT NULL,
    baseline_value  REAL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    post_value      REAL,
    window_sec      INTEGER NOT NULL DEFAULT 1800,
    verdict         TEXT,
    evaluated_at    TIMESTAMPTZ,
    approval_id     TEXT,
    human_decision  TEXT,
    rolled_back     BOOLEAN DEFAULT FALSE,
    rollback_success BOOLEAN,
    efficacy_score  REAL
);

CREATE INDEX IF NOT EXISTS idx_intervention_efficacy_pending
    ON events.intervention_efficacy (completed_at) WHERE verdict IS NULL;
CREATE INDEX IF NOT EXISTS idx_intervention_efficacy_zone
    ON events.intervention_efficacy (zone);

-- Phase 1 feedback / learning tables
CREATE TABLE IF NOT EXISTS events.agent_feedback (
    id BIGSERIAL PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'frontend',
    payload JSONB NOT NULL DEFAULT '{}',
    context JSONB NOT NULL DEFAULT '{}',
    user_id TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_feedback_target
    ON events.agent_feedback (target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_agent_feedback_type
    ON events.agent_feedback (feedback_type);
CREATE INDEX IF NOT EXISTS idx_agent_feedback_recorded_at
    ON events.agent_feedback (recorded_at);

CREATE TABLE IF NOT EXISTS events.agent_trajectories (
    id BIGSERIAL PRIMARY KEY,
    cycle_id TEXT,
    decision_id TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    trigger_events JSONB NOT NULL DEFAULT '[]',
    tool_calls JSONB NOT NULL DEFAULT '[]',
    world_state_snapshot JSONB NOT NULL DEFAULT '{}',
    outcome_summary JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_agent_trajectories_cycle
    ON events.agent_trajectories (cycle_id);
CREATE INDEX IF NOT EXISTS idx_agent_trajectories_timestamp
    ON events.agent_trajectories (timestamp);
"""


def get_engine() -> AsyncEngine | None:
    return _engine


async def init_db() -> AsyncEngine | None:
    """Initialize event store database. Returns engine or None."""
    global _engine

    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://hems:hems@postgres:5432/hems")
    if not db_url:
        logger.warning("No DATABASE_URL — event store disabled")
        return None

    is_postgres = "postgresql" in db_url

    if is_postgres:
        _engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
        )
    else:
        _engine = create_async_engine(db_url, echo=False)

        @event.listens_for(_engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            """Enable WAL mode and a busy timeout for SQLite backends."""
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    ddl = DDL_POSTGRES if is_postgres else DDL_SQLITE

    async with _engine.begin() as conn:
        for statement in ddl.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(text(stmt))

        # Migrate old schema: cycle_duration → cycle_duration_sec, add world_state_snapshot, cause_event_id
        if not is_postgres:
            cols = [r[1] for r in await conn.execute(text("PRAGMA table_info(llm_decisions)"))]
            if "cycle_duration" in cols and "cycle_duration_sec" not in cols:
                await conn.execute(text("ALTER TABLE llm_decisions RENAME COLUMN cycle_duration TO cycle_duration_sec"))
                logger.info("Migrated llm_decisions: cycle_duration → cycle_duration_sec")
            if "world_state_snapshot" not in cols:
                await conn.execute(text("ALTER TABLE llm_decisions ADD COLUMN world_state_snapshot TEXT DEFAULT '{}'"))
                logger.info("Migrated llm_decisions: added world_state_snapshot")
            if "cause_event_id" not in cols:
                await conn.execute(text("ALTER TABLE llm_decisions ADD COLUMN cause_event_id INTEGER"))
                logger.info("Migrated llm_decisions: added cause_event_id")
            # Create the cause index unconditionally now that the column is
            # guaranteed present (covers both fresh and migrated DBs).
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_llm_decisions_cause ON llm_decisions(cause_event_id)")
            )
            # Cost/energy metering columns (Group E) — all nullable
            for _col, _type in (
                ("prompt_tokens", "INTEGER"),
                ("completion_tokens", "INTEGER"),
                ("gpu_util_pct", "REAL"),
                ("gpu_power_w", "REAL"),
            ):
                if _col not in cols:
                    await conn.execute(text(f"ALTER TABLE llm_decisions ADD COLUMN {_col} {_type}"))
                    logger.info(f"Migrated llm_decisions: added {_col}")

            # Phase 0 HITL extension for intervention_efficacy
            ie_cols = [r[1] for r in await conn.execute(text("PRAGMA table_info(intervention_efficacy)"))]
            for _col, _type in (
                ("approval_id", "TEXT"),
                ("human_decision", "TEXT"),
                ("rolled_back", "INTEGER DEFAULT 0"),
                ("rollback_success", "INTEGER"),
                ("efficacy_score", "REAL"),
            ):
                if _col not in ie_cols:
                    await conn.execute(text(f"ALTER TABLE intervention_efficacy ADD COLUMN {_col} {_type}"))
                    logger.info(f"Migrated intervention_efficacy: added {_col}")
        else:
            # PostgreSQL: same idempotent ALTER for older deployments
            try:
                await conn.execute(
                    text("ALTER TABLE events.llm_decisions ADD COLUMN IF NOT EXISTS cause_event_id BIGINT")
                )
                await conn.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_llm_decisions_cause ON events.llm_decisions(cause_event_id)")
                )
                for _col, _type in (
                    ("prompt_tokens", "INTEGER"),
                    ("completion_tokens", "INTEGER"),
                    ("gpu_util_pct", "REAL"),
                    ("gpu_power_w", "REAL"),
                ):
                    await conn.execute(
                        text(f"ALTER TABLE events.llm_decisions ADD COLUMN IF NOT EXISTS {_col} {_type}")
                    )

                # Phase 0 HITL extension for intervention_efficacy
                for _col, _type in (
                    ("approval_id", "TEXT"),
                    ("human_decision", "TEXT"),
                    ("rolled_back", "BOOLEAN DEFAULT FALSE"),
                    ("rollback_success", "BOOLEAN"),
                    ("efficacy_score", "REAL"),
                ):
                    await conn.execute(
                        text(f"ALTER TABLE events.intervention_efficacy ADD COLUMN IF NOT EXISTS {_col} {_type}")
                    )
            except Exception:
                pass

    logger.info(f"Event store initialized ({'PostgreSQL' if is_postgres else 'SQLite'})")
    return _engine
