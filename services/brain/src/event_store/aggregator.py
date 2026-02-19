"""
HourlyAggregator: Background task that rolls up raw events into
hourly_aggregates (Data Mart) and handles retention cleanup.
SQLite and PostgreSQL compatible.

Runs every 10 minutes. For each unprocessed hour, queries raw_events
and llm_decisions, computes per-zone statistics, and UPSERTs into
hourly_aggregates.

Retention: raw_events 730 days, llm_decisions 730 days.
Cleanup runs once daily at 03:00 UTC.
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

IS_POSTGRES = "postgresql" in os.getenv("DATABASE_URL", "")


class HourlyAggregator:
    LOOP_INTERVAL = 600  # 10 minutes
    RAW_RETENTION_DAYS = 730       # 2 years (ML seasonal pattern learning)
    DECISION_RETENTION_DAYS = 730  # 2 years (LLM quality trend analysis)
    CLEANUP_HOUR_UTC = 3

    def __init__(self, engine: AsyncEngine):
        self._engine = engine
        self._running = False
        self._last_cleanup_date: str | None = None

    async def start(self):
        """Start the background aggregation loop."""
        self._running = True
        logger.info("HourlyAggregator started (every {}s)", self.LOOP_INTERVAL)
        while self._running:
            await asyncio.sleep(self.LOOP_INTERVAL)
            try:
                await self.aggregate_pending_hours()
                await self._maybe_cleanup()
            except Exception as e:
                logger.error("HourlyAggregator error: {}", e)

    async def stop(self):
        self._running = False
        logger.info("HourlyAggregator stopped")

    async def aggregate_pending_hours(self):
        """Process all completed hours that haven't been aggregated yet."""
        now = datetime.now(timezone.utc)
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        tp = "events." if IS_POSTGRES else ""

        async with self._engine.begin() as conn:
            row = await conn.execute(
                text(f"SELECT last_aggregated_hour FROM {tp}aggregation_state WHERE id = 1")
            )
            result = row.fetchone()
            last_hour = result[0] if result and result[0] else None

            if last_hour is None:
                # First run: find the earliest raw event
                row = await conn.execute(text(f"SELECT MIN(timestamp) FROM {tp}raw_events"))
                earliest = row.scalar()
                if earliest is None:
                    return  # No data yet
                if isinstance(earliest, str):
                    earliest = datetime.fromisoformat(earliest)
                last_hour = earliest.replace(minute=0, second=0, microsecond=0)
            elif isinstance(last_hour, str):
                last_hour = datetime.fromisoformat(last_hour)

            if last_hour.tzinfo is None:
                last_hour = last_hour.replace(tzinfo=timezone.utc)

            # Process each completed hour
            hour = last_hour
            hours_processed = 0
            while hour < current_hour_start:
                next_hour = hour + timedelta(hours=1)
                await self._aggregate_hour(conn, hour, next_hour, tp)
                hour = next_hour
                hours_processed += 1

                # Limit batch to 24 hours per run to avoid long transactions
                if hours_processed >= 24:
                    break

            if hours_processed > 0:
                # Update watermark — use isoformat strings for SQLite compatibility
                await conn.execute(
                    text(f"UPDATE {tp}aggregation_state SET last_aggregated_hour = :hour, last_run_at = :now WHERE id = 1"),
                    {"hour": hour.isoformat(), "now": now.isoformat()},
                )
                logger.info("Aggregated {} hour(s), watermark at {}", hours_processed, hour)

    async def _aggregate_hour(self, conn, hour_start: datetime, hour_end: datetime, tp: str):
        """Aggregate a single hour of data into hourly_aggregates."""
        start_str = hour_start.isoformat()
        end_str = hour_end.isoformat()

        zones: dict = {}

        if IS_POSTGRES:
            # Per-zone per-channel sensor stats (Postgres JSON operators)
            zone_rows = await conn.execute(
                text(f"""
                    SELECT zone,
                           data->>'channel' AS channel,
                           AVG((data->>'value')::float) AS avg_val,
                           MAX((data->>'value')::float) AS max_val,
                           MIN((data->>'value')::float) AS min_val,
                           COUNT(*) AS cnt
                    FROM {tp}raw_events
                    WHERE timestamp >= :start AND timestamp < :end
                      AND event_type = 'sensor_reading'
                      AND data->>'value' IS NOT NULL
                    GROUP BY zone, data->>'channel'
                """),
                {"start": start_str, "end": end_str},
            )
            for row in zone_rows:
                zone_id = row[0] or "unknown"
                channel = row[1]
                if zone_id not in zones:
                    zones[zone_id] = {}
                zones[zone_id][f"avg_{channel}"] = round(row[2], 2) if row[2] else None
                zones[zone_id][f"max_{channel}"] = round(row[3], 2) if row[3] else None
                zones[zone_id][f"min_{channel}"] = round(row[4], 2) if row[4] else None
                zones[zone_id][f"count_{channel}"] = row[5]

            # WorldModel event counts per zone (Postgres only)
            wm_rows = await conn.execute(
                text(f"""
                    SELECT zone, event_type, COUNT(*)
                    FROM {tp}raw_events
                    WHERE timestamp >= :start AND timestamp < :end
                      AND event_type LIKE 'world_model_%%'
                    GROUP BY zone, event_type
                """),
                {"start": start_str, "end": end_str},
            )
            for row in wm_rows:
                zone_id = row[0] or "unknown"
                if zone_id not in zones:
                    zones[zone_id] = {}
                zones[zone_id][row[1]] = row[2]
        else:
            # SQLite: simple event-type count grouped by zone
            rows = await conn.execute(
                text(f"SELECT zone, event_type, COUNT(*) FROM {tp}raw_events WHERE timestamp >= :start AND timestamp < :end GROUP BY zone, event_type"),
                {"start": start_str, "end": end_str},
            )
            for row in rows:
                zone_id = row[0] or "unknown"
                if zone_id not in zones:
                    zones[zone_id] = {}
                zones[zone_id][row[1]] = row[2]

        # LLM decision stats
        dr = await conn.execute(
            text(f"SELECT COUNT(*), COALESCE(SUM(total_tool_calls), 0) FROM {tp}llm_decisions WHERE timestamp >= :start AND timestamp < :end"),
            {"start": start_str, "end": end_str},
        )
        d = dr.fetchone()
        llm_cycles = d[0] if d else 0
        total_tool_calls = d[1] if d else 0

        # Count tasks created from tool_calls JSON (Postgres only — requires jsonb_array_elements)
        tasks_created = 0
        if IS_POSTGRES:
            tasks_row = await conn.execute(
                text(f"""
                    SELECT COUNT(*)
                    FROM {tp}llm_decisions,
                         jsonb_array_elements(tool_calls) AS tc
                    WHERE timestamp >= :start AND timestamp < :end
                      AND tc->>'tool' = 'create_task'
                """),
                {"start": start_str, "end": end_str},
            )
            tasks_created = tasks_row.scalar() or 0

        # UPSERT aggregate
        if IS_POSTGRES:
            await conn.execute(
                text(f"""
                    INSERT INTO {tp}hourly_aggregates (hub_id, period_start, zones, tasks_created, llm_cycles, device_health)
                    VALUES ('hems-brain', :period_start, CAST(:zones AS jsonb), :tasks_created, :llm_cycles, CAST(:device_health AS jsonb))
                    ON CONFLICT (hub_id, period_start) DO UPDATE SET
                        zones = EXCLUDED.zones,
                        tasks_created = EXCLUDED.tasks_created,
                        llm_cycles = EXCLUDED.llm_cycles,
                        device_health = EXCLUDED.device_health
                """),
                {"period_start": start_str, "zones": json.dumps(zones), "tasks_created": tasks_created,
                 "llm_cycles": llm_cycles, "device_health": json.dumps({"total_tool_calls": total_tool_calls})},
            )
        else:
            await conn.execute(
                text(f"""
                    INSERT OR REPLACE INTO {tp}hourly_aggregates (hub_id, period_start, zones, tasks_created, llm_cycles, device_health)
                    VALUES ('hems-brain', :period_start, :zones, :tasks_created, :llm_cycles, :device_health)
                """),
                {"period_start": start_str, "zones": json.dumps(zones), "tasks_created": tasks_created,
                 "llm_cycles": llm_cycles, "device_health": json.dumps({"total_tool_calls": total_tool_calls})},
            )

    async def _maybe_cleanup(self):
        """Run retention cleanup once per day at CLEANUP_HOUR_UTC."""
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        if now.hour != self.CLEANUP_HOUR_UTC or self._last_cleanup_date == today:
            return

        self._last_cleanup_date = today
        raw_cutoff = (now - timedelta(days=self.RAW_RETENTION_DAYS)).isoformat()
        decision_cutoff = (now - timedelta(days=self.DECISION_RETENTION_DAYS)).isoformat()
        tp = "events." if IS_POSTGRES else ""

        async with self._engine.begin() as conn:
            r1 = await conn.execute(
                text(f"DELETE FROM {tp}raw_events WHERE timestamp < :cutoff"),
                {"cutoff": raw_cutoff},
            )
            r2 = await conn.execute(
                text(f"DELETE FROM {tp}llm_decisions WHERE timestamp < :cutoff"),
                {"cutoff": decision_cutoff},
            )
            logger.info("Retention cleanup: deleted {} raw events, {} decisions", r1.rowcount, r2.rowcount)
