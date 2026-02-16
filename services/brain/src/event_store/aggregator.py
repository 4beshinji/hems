"""
HourlyAggregator: Background task that rolls up raw events into
hourly_aggregates (Data Mart). SQLite and PostgreSQL compatible.
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
    RAW_RETENTION_DAYS = 90
    CLEANUP_HOUR_UTC = 3

    def __init__(self, engine: AsyncEngine):
        self._engine = engine
        self._running = False
        self._last_cleanup_date: str | None = None

    async def start(self):
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

    async def aggregate_pending_hours(self):
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
                row = await conn.execute(text(f"SELECT MIN(timestamp) FROM {tp}raw_events"))
                earliest = row.scalar()
                if earliest is None:
                    return
                if isinstance(earliest, str):
                    earliest = datetime.fromisoformat(earliest)
                last_hour = earliest.replace(minute=0, second=0, microsecond=0)
            elif isinstance(last_hour, str):
                last_hour = datetime.fromisoformat(last_hour)

            if last_hour.tzinfo is None:
                last_hour = last_hour.replace(tzinfo=timezone.utc)

            hour = last_hour
            hours_processed = 0
            while hour < current_hour_start:
                next_hour = hour + timedelta(hours=1)
                await self._aggregate_hour(conn, hour, next_hour, tp)
                hour = next_hour
                hours_processed += 1
                if hours_processed >= 24:
                    break

            if hours_processed > 0:
                await conn.execute(
                    text(f"UPDATE {tp}aggregation_state SET last_aggregated_hour = :hour, last_run_at = :now WHERE id = 1"),
                    {"hour": hour.isoformat(), "now": now.isoformat()},
                )
                logger.info("Aggregated {} hour(s), watermark at {}", hours_processed, hour)

    async def _aggregate_hour(self, conn, hour_start, hour_end, tp):
        start_str = hour_start.isoformat()
        end_str = hour_end.isoformat()

        # Count events per zone
        rows = await conn.execute(
            text(f"SELECT zone, event_type, COUNT(*) FROM {tp}raw_events WHERE timestamp >= :start AND timestamp < :end GROUP BY zone, event_type"),
            {"start": start_str, "end": end_str},
        )
        zones = {}
        for row in rows:
            zone_id = row[0] or "unknown"
            if zone_id not in zones:
                zones[zone_id] = {}
            zones[zone_id][row[1]] = row[2]

        # LLM decisions
        dr = await conn.execute(
            text(f"SELECT COUNT(*), COALESCE(SUM(total_tool_calls), 0) FROM {tp}llm_decisions WHERE timestamp >= :start AND timestamp < :end"),
            {"start": start_str, "end": end_str},
        )
        d = dr.fetchone()
        llm_cycles = d[0] if d else 0
        total_tool_calls = d[1] if d else 0

        # UPSERT
        if IS_POSTGRES:
            await conn.execute(
                text(f"""
                    INSERT INTO {tp}hourly_aggregates (hub_id, period_start, zones, tasks_created, llm_cycles, device_health)
                    VALUES ('hems-brain', :period_start, :zones::jsonb, 0, :llm_cycles, :device_health::jsonb)
                    ON CONFLICT (hub_id, period_start) DO UPDATE SET
                        zones = EXCLUDED.zones, llm_cycles = EXCLUDED.llm_cycles, device_health = EXCLUDED.device_health
                """),
                {"period_start": start_str, "zones": json.dumps(zones), "llm_cycles": llm_cycles,
                 "device_health": json.dumps({"total_tool_calls": total_tool_calls})},
            )
        else:
            await conn.execute(
                text(f"""
                    INSERT OR REPLACE INTO hourly_aggregates (hub_id, period_start, zones, tasks_created, llm_cycles, device_health)
                    VALUES ('hems-brain', :period_start, :zones, 0, :llm_cycles, :device_health)
                """),
                {"period_start": start_str, "zones": json.dumps(zones), "llm_cycles": llm_cycles,
                 "device_health": json.dumps({"total_tool_calls": total_tool_calls})},
            )

    async def _maybe_cleanup(self):
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        if now.hour != self.CLEANUP_HOUR_UTC or self._last_cleanup_date == today:
            return

        self._last_cleanup_date = today
        cutoff = (now - timedelta(days=self.RAW_RETENTION_DAYS)).isoformat()
        tp = "events." if IS_POSTGRES else ""

        async with self._engine.begin() as conn:
            r1 = await conn.execute(text(f"DELETE FROM {tp}raw_events WHERE timestamp < :cutoff"), {"cutoff": cutoff})
            r2 = await conn.execute(text(f"DELETE FROM {tp}llm_decisions WHERE timestamp < :cutoff"), {"cutoff": cutoff})
            logger.info("Retention cleanup: deleted {} raw events, {} decisions", r1.rowcount, r2.rowcount)
