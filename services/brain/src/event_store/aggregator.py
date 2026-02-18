"""
HourlyAggregator: Background task that rolls up raw events into
hourly_aggregates (Data Mart) and handles retention cleanup.

Runs every 10 minutes. For each unprocessed hour, queries raw_events
and llm_decisions, computes per-zone statistics, and UPSERTs into
hourly_aggregates. Output JSON matches CITY_SCALE_VISION.md schema.

Retention: raw_events 90 days, llm_decisions 90 days.
Cleanup runs once daily at 03:00 UTC.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class HourlyAggregator:
    LOOP_INTERVAL = 600  # 10 minutes
    RAW_RETENTION_DAYS = 90
    DECISION_RETENTION_DAYS = 90
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

        async with self._engine.begin() as conn:
            # Get last aggregated hour
            row = await conn.execute(
                text("SELECT last_aggregated_hour FROM events.aggregation_state WHERE id = 1")
            )
            result = row.fetchone()
            last_hour = result[0] if result and result[0] else None

            if last_hour is None:
                # First run: find the earliest raw event
                row = await conn.execute(
                    text("SELECT MIN(timestamp) FROM events.raw_events")
                )
                earliest = row.scalar()
                if earliest is None:
                    return  # No data yet
                last_hour = earliest.replace(minute=0, second=0, microsecond=0)
            elif last_hour.tzinfo is None:
                last_hour = last_hour.replace(tzinfo=timezone.utc)

            # Process each completed hour
            hour = last_hour
            hours_processed = 0
            while hour < current_hour_start:
                next_hour = hour + timedelta(hours=1)
                await self._aggregate_hour(conn, hour, next_hour)
                hour = next_hour
                hours_processed += 1

                # Limit batch to 24 hours per run to avoid long transactions
                if hours_processed >= 24:
                    break

            if hours_processed > 0:
                # Update watermark
                await conn.execute(
                    text("""
                        UPDATE events.aggregation_state
                        SET last_aggregated_hour = :hour, last_run_at = :now
                        WHERE id = 1
                    """),
                    {"hour": hour, "now": now},
                )
                logger.info("Aggregated {} hour(s), watermark at {}", hours_processed, hour)

    async def _aggregate_hour(self, conn, hour_start: datetime, hour_end: datetime):
        """Aggregate a single hour of data into hourly_aggregates."""
        # Per-zone sensor stats
        zone_rows = await conn.execute(
            text("""
                SELECT zone,
                       data->>'channel' AS channel,
                       AVG((data->>'value')::float) AS avg_val,
                       MAX((data->>'value')::float) AS max_val,
                       MIN((data->>'value')::float) AS min_val,
                       COUNT(*) AS cnt
                FROM events.raw_events
                WHERE timestamp >= :start AND timestamp < :end
                  AND event_type = 'sensor_reading'
                  AND data->>'value' IS NOT NULL
                GROUP BY zone, data->>'channel'
            """),
            {"start": hour_start, "end": hour_end},
        )

        zones: dict = {}
        for row in zone_rows:
            zone_id = row[0]
            channel = row[1]
            if zone_id not in zones:
                zones[zone_id] = {}
            zones[zone_id][f"avg_{channel}"] = round(row[2], 2) if row[2] else None
            zones[zone_id][f"max_{channel}"] = round(row[3], 2) if row[3] else None
            zones[zone_id][f"min_{channel}"] = round(row[4], 2) if row[4] else None
            zones[zone_id][f"count_{channel}"] = row[5]

        # WorldModel event counts per zone
        wm_rows = await conn.execute(
            text("""
                SELECT zone, event_type, COUNT(*)
                FROM events.raw_events
                WHERE timestamp >= :start AND timestamp < :end
                  AND event_type LIKE 'world_model_%%'
                GROUP BY zone, event_type
            """),
            {"start": hour_start, "end": hour_end},
        )
        for row in wm_rows:
            zone_id = row[0]
            if zone_id not in zones:
                zones[zone_id] = {}
            zones[zone_id][row[1]] = row[2]

        # LLM decision stats
        decision_row = await conn.execute(
            text("""
                SELECT COUNT(*),
                       COALESCE(SUM(total_tool_calls), 0)
                FROM events.llm_decisions
                WHERE timestamp >= :start AND timestamp < :end
            """),
            {"start": hour_start, "end": hour_end},
        )
        dr = decision_row.fetchone()
        llm_cycles = dr[0] if dr else 0
        total_tool_calls = dr[1] if dr else 0

        # Count tasks created (from tool_calls JSON)
        tasks_row = await conn.execute(
            text("""
                SELECT COUNT(*)
                FROM events.llm_decisions,
                     jsonb_array_elements(tool_calls) AS tc
                WHERE timestamp >= :start AND timestamp < :end
                  AND tc->>'tool' = 'create_task'
            """),
            {"start": hour_start, "end": hour_end},
        )
        tasks_created = tasks_row.scalar() or 0

        import json
        # UPSERT aggregate
        await conn.execute(
            text("""
                INSERT INTO events.hourly_aggregates
                    (hub_id, period_start, zones, tasks_created, llm_cycles, device_health)
                VALUES
                    ('soms-brain', :period_start, CAST(:zones AS jsonb), :tasks_created,
                     :llm_cycles, CAST(:device_health AS jsonb))
                ON CONFLICT (hub_id, period_start) DO UPDATE SET
                    zones = EXCLUDED.zones,
                    tasks_created = EXCLUDED.tasks_created,
                    llm_cycles = EXCLUDED.llm_cycles,
                    device_health = EXCLUDED.device_health
            """),
            {
                "period_start": hour_start,
                "zones": json.dumps(zones),
                "tasks_created": tasks_created,
                "llm_cycles": llm_cycles,
                "device_health": json.dumps({"total_tool_calls": total_tool_calls}),
            },
        )

    async def _maybe_cleanup(self):
        """Run retention cleanup once per day at CLEANUP_HOUR_UTC."""
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        if now.hour != self.CLEANUP_HOUR_UTC:
            return
        if self._last_cleanup_date == today:
            return

        self._last_cleanup_date = today
        raw_cutoff = now - timedelta(days=self.RAW_RETENTION_DAYS)
        decision_cutoff = now - timedelta(days=self.DECISION_RETENTION_DAYS)

        async with self._engine.begin() as conn:
            r1 = await conn.execute(
                text("DELETE FROM events.raw_events WHERE timestamp < :cutoff"),
                {"cutoff": raw_cutoff},
            )
            r2 = await conn.execute(
                text("DELETE FROM events.llm_decisions WHERE timestamp < :cutoff"),
                {"cutoff": decision_cutoff},
            )
            logger.info(
                "Retention cleanup: deleted {} raw events, {} decisions",
                r1.rowcount, r2.rowcount,
            )
