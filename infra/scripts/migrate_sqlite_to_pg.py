#!/usr/bin/env python3
"""
SQLite → PostgreSQL migration script for HEMS.

Migrates two SQLite sources into a single PostgreSQL database:
  1. Backend SQLite  (hems_backend_data/hems.db) → PG public schema
     Tables: all ORM-managed tables from services/backend/models.py
  2. Brain event_store SQLite (hems_brain_data/hems.db) → PG events schema
     Tables: raw_events, llm_decisions, hourly_aggregates, aggregation_state,
             world_events, intervention_efficacy

Usage:
    # Dry-run (default — no writes)
    python infra/scripts/migrate_sqlite_to_pg.py --dry-run \\
        --backend-sqlite /path/to/backend/hems.db \\
        --brain-sqlite   /path/to/brain/hems.db \\
        --pg-url postgresql+psycopg2://hems:pass@localhost:5442/hems

    # Execute migration
    python infra/scripts/migrate_sqlite_to_pg.py --execute \\
        --backend-sqlite /path/to/backend/hems.db \\
        --brain-sqlite   /path/to/brain/hems.db \\
        --pg-url postgresql+psycopg2://hems:pass@localhost:5442/hems \\
        --mode skip-nonempty

Idempotence modes (--mode):
    skip-nonempty   Skip any PG table that already has rows [DEFAULT — safest]
    truncate        DELETE all rows from PG table before inserting
    upsert          INSERT … ON CONFLICT (id) DO NOTHING (requires id PK)

Notes:
    - SQLite databases are never modified (read-only).
    - After migration, SERIAL/BIGSERIAL sequences are advanced to max(id)+1
      to prevent PK collisions on first new INSERT.
    - All timestamps are converted from naive UTC → UTC-aware.
    - JSON/JSONB text columns are parsed and re-serialised as Python dicts
      so that PostgreSQL stores native JSONB rather than escaped strings.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Column classification helpers
# ---------------------------------------------------------------------------

# Event-store tables whose "data" column is JSON stored as TEXT in SQLite.
_JSONB_COLUMNS: dict[str, set[str]] = {
    "raw_events": {"data"},
    "llm_decisions": {"trigger_events", "tool_calls", "world_state_snapshot"},
    "hourly_aggregates": {"zones", "device_health"},
    "world_events": {"data"},
}

# Backend ORM tables have JSON/JSON columns handled via SQLAlchemy — we keep
# them as-is (already Python dicts/lists when read via sqlite3 Row).
# But sqlite3 returns them as strings, so we need to parse them too.
_BACKEND_JSON_COLUMNS: dict[str, set[str]] = {
    "devices": {"capabilities", "channels", "units", "last_state", "last_value"},
    "scenes": {"actions"},
    "automation_rules": {"trigger_config", "actions"},
    "device_action_log": {"params"},
}

# Event-store table order: world_events must come before llm_decisions
# (FK: llm_decisions.cause_event_id → world_events.id).
_EVENTSTORE_TABLE_ORDER = [
    "world_events",
    "raw_events",
    "llm_decisions",
    "hourly_aggregates",
    "aggregation_state",
    "intervention_efficacy",
]

_EVENTSTORE_PG_SCHEMA = "events"


# ---------------------------------------------------------------------------
# Type conversion utilities
# ---------------------------------------------------------------------------


def convert_timestamp(value: Any) -> Any:
    """
    Convert a naive UTC datetime string (SQLite) to a UTC-aware datetime
    string suitable for PostgreSQL TIMESTAMPTZ.

    Accepted forms:
      - None / empty string → None
      - Already a datetime with tzinfo → returned as-is ISO string
      - "YYYY-MM-DD HH:MM:SS[.ffffff]" → UTC-aware ISO string
      - Anything else → passed through unchanged
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.isoformat()
    if isinstance(value, str):
        # Strip trailing 'Z' or existing tz info then re-attach UTC
        v = value.strip()
        if not v:
            return None
        try:
            # Handle "YYYY-MM-DD HH:MM:SS.ffffff" and "YYYY-MM-DD HH:MM:SS"
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(v.rstrip("Z"), fmt)
                    return dt.replace(tzinfo=UTC).isoformat()
                except ValueError:
                    continue
        except Exception:
            pass
    return value


def convert_json(value: Any) -> Any:
    """
    Parse a JSON string from SQLite into a Python object.
    If already a dict/list, return unchanged.
    None/empty → None.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            logger.warning(f"Cannot parse JSON: {v[:80]!r} — keeping as string")
            return value
    return value


def convert_bool(value: Any) -> Any:
    """
    SQLite stores booleans as 0/1 integers.
    PostgreSQL accepts Python True/False natively via psycopg2.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    return value


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------


def sqlite_connect(path: str) -> sqlite3.Connection:
    """Open a read-only SQLite connection."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    if not sqlite_table_exists(conn, table):
        return 0
    cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row["name"] for row in cur.fetchall()]


def sqlite_read_all(conn: sqlite3.Connection, table: str) -> list[dict]:
    cur = conn.execute(f"SELECT * FROM {table}")
    return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Row transformation
# ---------------------------------------------------------------------------

# Timestamp column name heuristics (match names used across both schemas)
_TS_COLUMN_SUFFIXES = (
    "timestamp",
    "created_at",
    "updated_at",
    "recorded_at",
    "last_seen",
    "last_seen_reported",
    "dispatched_at",
    "completed_at",
    "expires_at",
    "dismissed_at",
    "accepted_at",
    "deadline",
    "last_reminded_at",
    "locked_start",
    "generated_at",
    "start_ts",
    "end_ts",
    "last_purchased_at",
    "next_purchase_at",
    "purchased_at",
    "last_executed_at",
    "last_fired_at",
    "last_aggregated_hour",
    "last_run_at",
    "period_start",
    "created_at",
    "evaluated_at",
    "learned_at",
    "registered_at",
    "last_seen_at",
)


def transform_row(
    row: dict,
    table: str,
    json_cols: set[str] | None = None,
) -> dict:
    """
    Apply type conversions to a row dict:
      - Timestamp columns: naive UTC string → UTC-aware ISO string
      - JSON columns: TEXT → Python dict/list
      - Boolean columns: 0/1 int → True/False
    """
    result = {}
    json_set = json_cols or set()

    for col, val in row.items():
        col_lower = col.lower()

        # JSON/JSONB columns
        if col in json_set:
            result[col] = convert_json(val)
            continue

        # Timestamp heuristic
        if any(col_lower == suf or col_lower.endswith("_" + suf) for suf in _TS_COLUMN_SUFFIXES):
            result[col] = convert_timestamp(val)
            continue

        # Boolean heuristic: columns named is_* or enabled or similar
        if col_lower.startswith("is_") or col_lower in (
            "enabled",
            "invalidated",
            "require_confirm",
            "success",
        ):
            result[col] = convert_bool(val)
            continue

        result[col] = val

    return result


# ---------------------------------------------------------------------------
# PostgreSQL helpers (synchronous psycopg2)
# ---------------------------------------------------------------------------


def pg_connect(pg_url: str):
    """Return a psycopg2 connection from a SQLAlchemy-style DSN."""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError as exc:
        raise RuntimeError("psycopg2 is required for migration. Install: pip install psycopg2-binary") from exc

    # Convert asyncpg DSN to psycopg2 DSN if needed
    url = pg_url
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgresql+psycopg2://", "postgresql://")

    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    conn.autocommit = False
    return conn


def pg_table_count(conn, schema: str, table: str) -> int:
    """Return row count of a PostgreSQL table (0 if table doesn't exist)."""
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
        row = cur.fetchone()
        return row["count"] if row else 0
    except Exception:
        conn.rollback()
        return -1  # table might not exist
    finally:
        cur.close()


def pg_table_exists(conn, schema: str, table: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
            (schema, table),
        )
        return cur.fetchone() is not None
    finally:
        cur.close()


def pg_setval(conn, schema: str, table: str, id_col: str = "id") -> None:
    """Advance the SERIAL/BIGSERIAL sequence to max(id)+1."""
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT MAX({id_col}) FROM {schema}.{table}")
        row = cur.fetchone()
        max_id = row[id_col] if row else None
        if max_id is None:
            return
        # Get sequence name and advance it
        cur.execute(
            "SELECT pg_get_serial_sequence(%s, %s) AS seq",
            (f"{schema}.{table}", id_col),
        )
        seq_row = cur.fetchone()
        if seq_row and seq_row["seq"]:
            cur.execute("SELECT setval(%s, %s)", (seq_row["seq"], max_id))
            logger.debug(f"  setval({seq_row['seq']}, {max_id})")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.warning(f"  setval failed for {schema}.{table}: {exc}")
    finally:
        cur.close()


def pg_insert_rows(
    conn,
    schema: str,
    table: str,
    rows: list[dict],
    mode: str,
    chunk_size: int = 1000,
) -> int:
    """
    Insert rows into a PostgreSQL table.

    mode:
        skip-nonempty — caller guarantees table is empty; plain INSERT
        truncate      — table was already truncated by caller; plain INSERT
        upsert        — INSERT … ON CONFLICT (id) DO NOTHING
    Returns number of rows actually inserted.
    """
    if not rows:
        return 0

    cols = list(rows[0].keys())
    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(f"%({c})s" for c in cols)

    if mode == "upsert":
        sql = f'INSERT INTO {schema}."{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING'
    else:
        sql = f'INSERT INTO {schema}."{table}" ({col_list}) VALUES ({placeholders})'

    cur = conn.cursor()
    inserted = 0
    try:
        for start in range(0, len(rows), chunk_size):
            chunk = rows[start : start + chunk_size]
            cur.executemany(sql, chunk)
            conn.commit()
            inserted += len(chunk)
            logger.debug(f"  {schema}.{table}: inserted {inserted}/{len(rows)}")
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"Insert failed for {schema}.{table}: {exc}") from exc
    finally:
        cur.close()

    return inserted


# ---------------------------------------------------------------------------
# Backend migration (ORM-managed tables → public schema)
# ---------------------------------------------------------------------------

# Ordered list of backend tables to migrate.
# Tables with FK dependencies must come after the tables they reference.
# Base tables first, then tables with FKs.
_BACKEND_TABLE_ORDER = [
    # No FK dependencies
    "users",
    "system_stats",
    "shopping_items",
    "purchase_history",
    "frequent_places",
    "mobile_devices",
    "biometric_readings",
    "bridge_status_log",
    "device_action_log",
    "timeseries",
    # voice_capsules before play_log (FK)
    "voice_capsules",
    "voice_capsule_play_log",
    # conversations before messages (FK)
    "conversations",
    "messages",
    # tasks before scheduled_blocks, dismiss_log (FK)
    "tasks",
    "scheduled_blocks",
    "dismiss_log",
    "task_preferences",
    # devices — no FK, but large
    "devices",
    "scenes",
    "automation_rules",
    "classifier_cache",
]


def get_backend_tables(sqlite_conn: sqlite3.Connection) -> list[str]:
    """Return ordered list of backend tables that exist in the SQLite DB."""
    existing = set()
    cur = sqlite_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    for row in cur.fetchall():
        existing.add(row[0])

    ordered = [t for t in _BACKEND_TABLE_ORDER if t in existing]
    # Add any tables present in SQLite but not in our ordered list (future-proof)
    extras = sorted(existing - set(_BACKEND_TABLE_ORDER) - {"sqlite_sequence", "sqlite_master"})
    if extras:
        logger.warning(f"Extra tables in backend SQLite not in migration order: {extras}")
    return ordered + extras


def migrate_backend(
    sqlite_path: str,
    pg_conn,
    mode: str,
    dry_run: bool,
) -> dict[str, tuple[int, int]]:
    """
    Migrate backend SQLite → PostgreSQL public schema.

    Returns dict: table_name → (sqlite_count, pg_inserted)
    """
    results: dict[str, tuple[int, int]] = {}

    sqlite_conn = sqlite_connect(sqlite_path)
    tables = get_backend_tables(sqlite_conn)

    logger.info(f"Backend tables to migrate: {tables}")

    for table in tables:
        src_count = sqlite_count(sqlite_conn, table)
        pg_count = pg_table_count(pg_conn, "public", table) if not dry_run else -1

        if dry_run:
            # In dry-run, just check PG count as well for reporting
            pg_count = pg_table_count(pg_conn, "public", table)
            logger.info(f"  [DRY-RUN] {table}: SQLite={src_count}, PG={pg_count}")
            results[table] = (src_count, 0)
            continue

        # Idempotence check
        if mode == "skip-nonempty" and pg_count > 0:
            logger.info(f"  SKIP {table}: PG already has {pg_count} rows")
            results[table] = (src_count, 0)
            continue

        if mode == "truncate" and pg_count > 0:
            cur = pg_conn.cursor()
            try:
                cur.execute(f'TRUNCATE TABLE public."{table}" CASCADE')
                pg_conn.commit()
                logger.info(f"  TRUNCATED public.{table}")
            except Exception as exc:
                pg_conn.rollback()
                logger.error(f"  TRUNCATE failed for {table}: {exc}")
                results[table] = (src_count, -1)
                continue
            finally:
                cur.close()

        if src_count == 0:
            logger.info(f"  SKIP {table}: source is empty")
            results[table] = (0, 0)
            continue

        rows = sqlite_read_all(sqlite_conn, table)
        json_cols = _BACKEND_JSON_COLUMNS.get(table, set())
        transformed = [transform_row(r, table, json_cols) for r in rows]

        try:
            inserted = pg_insert_rows(pg_conn, "public", table, transformed, mode)
            logger.info(f"  OK {table}: {inserted}/{src_count} rows migrated")
            results[table] = (src_count, inserted)
        except RuntimeError as exc:
            logger.error(str(exc))
            results[table] = (src_count, -1)
            continue

        # Advance sequence
        pg_setval(pg_conn, "public", table)

    sqlite_conn.close()
    return results


# ---------------------------------------------------------------------------
# Event-store migration (brain SQLite → events schema)
# ---------------------------------------------------------------------------


def migrate_eventstore(
    sqlite_path: str,
    pg_conn,
    mode: str,
    dry_run: bool,
) -> dict[str, tuple[int, int]]:
    """
    Migrate brain event_store SQLite → PostgreSQL events schema.

    Returns dict: table_name → (sqlite_count, pg_inserted)
    """
    results: dict[str, tuple[int, int]] = {}

    sqlite_conn = sqlite_connect(sqlite_path)

    for table in _EVENTSTORE_TABLE_ORDER:
        if not sqlite_table_exists(sqlite_conn, table):
            logger.warning(f"  Event-store table not found in SQLite: {table} — skipping")
            continue

        src_count = sqlite_count(sqlite_conn, table)
        pg_schema = _EVENTSTORE_PG_SCHEMA

        if dry_run:
            pg_count = pg_table_count(pg_conn, pg_schema, table)
            logger.info(f"  [DRY-RUN] events.{table}: SQLite={src_count}, PG={pg_count}")
            results[table] = (src_count, 0)
            continue

        pg_count = pg_table_count(pg_conn, pg_schema, table)

        if mode == "skip-nonempty" and pg_count > 0:
            logger.info(f"  SKIP events.{table}: PG already has {pg_count} rows")
            results[table] = (src_count, 0)
            continue

        if mode == "truncate" and pg_count > 0:
            cur = pg_conn.cursor()
            try:
                # TRUNCATE with CASCADE to handle FK (llm_decisions → world_events)
                cur.execute(f'TRUNCATE TABLE {pg_schema}."{table}" CASCADE')
                pg_conn.commit()
                logger.info(f"  TRUNCATED {pg_schema}.{table}")
            except Exception as exc:
                pg_conn.rollback()
                logger.error(f"  TRUNCATE failed for events.{table}: {exc}")
                results[table] = (src_count, -1)
                continue
            finally:
                cur.close()

        if src_count == 0:
            logger.info(f"  SKIP events.{table}: source is empty")
            results[table] = (0, 0)
            continue

        rows = sqlite_read_all(sqlite_conn, table)
        json_cols = _JSONB_COLUMNS.get(table, set())
        transformed = [transform_row(r, table, json_cols) for r in rows]

        try:
            inserted = pg_insert_rows(pg_conn, pg_schema, table, transformed, mode)
            logger.info(f"  OK events.{table}: {inserted}/{src_count} rows migrated")
            results[table] = (src_count, inserted)
        except RuntimeError as exc:
            logger.error(str(exc))
            results[table] = (src_count, -1)
            continue

        # Advance SERIAL/BIGSERIAL sequence
        pg_setval(pg_conn, pg_schema, table)

    sqlite_conn.close()
    return results


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify(
    backend_sqlite: str | None,
    brain_sqlite: str | None,
    pg_conn,
) -> bool:
    """Compare row counts between SQLite sources and PostgreSQL. Returns True if all match."""
    ok = True

    if backend_sqlite:
        sqlite_conn = sqlite_connect(backend_sqlite)
        tables = get_backend_tables(sqlite_conn)
        logger.info("\n--- Verify: backend (public schema) ---")
        for table in tables:
            src = sqlite_count(sqlite_conn, table)
            dst = pg_table_count(pg_conn, "public", table)
            status = "OK" if src == dst else "MISMATCH"
            logger.info(f"  {status} {table}: SQLite={src}, PG={dst}")
            if src != dst:
                ok = False
        sqlite_conn.close()

    if brain_sqlite:
        sqlite_conn = sqlite_connect(brain_sqlite)
        logger.info("\n--- Verify: event_store (events schema) ---")
        for table in _EVENTSTORE_TABLE_ORDER:
            if not sqlite_table_exists(sqlite_conn, table):
                continue
            src = sqlite_count(sqlite_conn, table)
            dst = pg_table_count(pg_conn, "events", table)
            status = "OK" if src == dst else "MISMATCH"
            logger.info(f"  {status} events.{table}: SQLite={src}, PG={dst}")
            if src != dst:
                ok = False
        sqlite_conn.close()

    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_DEFAULT_BACKEND_SQLITE = "/var/lib/docker/volumes/hems_backend_data/_data/hems.db"
_DEFAULT_BRAIN_SQLITE = "/var/lib/docker/volumes/hems_brain_data/_data/hems.db"
_DEFAULT_PG_URL = "postgresql://hems:hems@localhost:5442/hems"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Migrate HEMS SQLite databases to PostgreSQL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--backend-sqlite",
        default=_DEFAULT_BACKEND_SQLITE,
        help=f"Path to backend SQLite DB (default: {_DEFAULT_BACKEND_SQLITE})",
    )
    p.add_argument(
        "--brain-sqlite",
        default=_DEFAULT_BRAIN_SQLITE,
        help=f"Path to brain event_store SQLite DB (default: {_DEFAULT_BRAIN_SQLITE})",
    )
    p.add_argument(
        "--pg-url",
        default=_DEFAULT_PG_URL,
        help=f"PostgreSQL DSN (default: {_DEFAULT_PG_URL})",
    )

    mode_group = p.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Count rows only, no writes [DEFAULT]",
    )
    mode_group.add_argument(
        "--execute",
        dest="dry_run",
        action="store_false",
        help="Actually perform the migration",
    )

    p.add_argument(
        "--mode",
        choices=["skip-nonempty", "truncate", "upsert"],
        default="skip-nonempty",
        help=(
            "Idempotence mode (only relevant with --execute): "
            "skip-nonempty=abort if PG table non-empty [DEFAULT], "
            "truncate=clear PG table first, "
            "upsert=INSERT ON CONFLICT DO NOTHING"
        ),
    )
    p.add_argument(
        "--verify-only",
        action="store_true",
        help="Skip migration; only compare row counts between SQLite and PG",
    )
    p.add_argument(
        "--skip-backend",
        action="store_true",
        help="Skip backend SQLite migration",
    )
    p.add_argument(
        "--skip-brain",
        action="store_true",
        help="Skip brain event_store SQLite migration",
    )
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, format="<level>{level: <8}</level> {message}", level="DEBUG")

    backend_sqlite = args.backend_sqlite if not args.skip_backend else None
    brain_sqlite = args.brain_sqlite if not args.skip_brain else None

    if args.verify_only:
        logger.info("Verify-only mode — connecting to PostgreSQL...")
        try:
            pg_conn = pg_connect(args.pg_url)
        except Exception as exc:
            logger.error(f"Cannot connect to PostgreSQL: {exc}")
            return 1
        ok = verify(backend_sqlite, brain_sqlite, pg_conn)
        pg_conn.close()
        return 0 if ok else 1

    if args.dry_run:
        logger.info("=== DRY-RUN mode — no data will be written ===")
    else:
        logger.info(f"=== EXECUTE mode — mode={args.mode} ===")

    # Connect to PostgreSQL (needed even for dry-run to show PG counts)
    try:
        pg_conn = pg_connect(args.pg_url)
        logger.info(f"Connected to PostgreSQL: {args.pg_url}")
    except Exception as exc:
        logger.error(f"Cannot connect to PostgreSQL: {exc}")
        return 1

    all_ok = True

    # --- Backend ---
    if backend_sqlite:
        import os

        if not os.path.exists(backend_sqlite):
            logger.warning(f"Backend SQLite not found: {backend_sqlite} — skipping")
        else:
            logger.info(f"\n=== Backend migration: {backend_sqlite} ===")
            backend_results = migrate_backend(backend_sqlite, pg_conn, args.mode, args.dry_run)
            errors = [t for t, (_, n) in backend_results.items() if n == -1]
            if errors:
                logger.error(f"Backend migration errors in: {errors}")
                all_ok = False

    # --- Brain event_store ---
    if brain_sqlite:
        import os

        if not os.path.exists(brain_sqlite):
            logger.warning(f"Brain SQLite not found: {brain_sqlite} — skipping")
        else:
            logger.info(f"\n=== Event-store migration: {brain_sqlite} ===")
            brain_results = migrate_eventstore(brain_sqlite, pg_conn, args.mode, args.dry_run)
            errors = [t for t, (_, n) in brain_results.items() if n == -1]
            if errors:
                logger.error(f"Event-store migration errors in: {errors}")
                all_ok = False

    # --- Verify ---
    if not args.dry_run and all_ok:
        logger.info("\n=== Post-migration verification ===")
        ok = verify(backend_sqlite, brain_sqlite, pg_conn)
        if not ok:
            logger.error("Verification FAILED — row count mismatch detected")
            all_ok = False
        else:
            logger.info("Verification PASSED — all counts match")

    pg_conn.close()

    if all_ok:
        logger.info("\nMigration complete.")
        return 0
    else:
        logger.error("\nMigration completed WITH ERRORS — check logs above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
