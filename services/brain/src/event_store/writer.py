"""
Async buffered event writer — writes to raw_events and llm_decisions.
SQLite and PostgreSQL compatible.
"""
import asyncio
import json
import os
import time
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

FLUSH_INTERVAL = 5  # seconds
IS_POSTGRES = "postgresql" in os.getenv("DATABASE_URL", "")


class EventWriter:
    def __init__(self, engine: AsyncEngine):
        self._engine = engine
        self._buffer: list[dict] = []
        self._running = False

    async def start(self):
        self._running = True
        logger.info("EventWriter started (flush every {}s)", FLUSH_INTERVAL)
        while self._running:
            await asyncio.sleep(FLUSH_INTERVAL)
            await self._flush()

    async def stop(self):
        self._running = False
        await self._flush()

    def record_sensor(self, zone: str, channel: str, value, device_id: str = "", topic: str = ""):
        self._buffer.append({
            "type": "sensor",
            "zone": zone,
            "event_type": "sensor_reading",
            "data": {"channel": channel, "value": value, "device_id": device_id, "topic": topic},
            "timestamp": time.time(),
        })

    def record_event(self, zone: str, event_type: str, data: dict = None):
        self._buffer.append({
            "type": "event",
            "zone": zone,
            "event_type": event_type,
            "data": data or {},
            "timestamp": time.time(),
        })

    def record_decision(self, cycle_duration: float, iterations: int,
                        total_tool_calls: int, trigger_events: list, tool_calls: list):
        self._buffer.append({
            "type": "decision",
            "cycle_duration": cycle_duration,
            "iterations": iterations,
            "total_tool_calls": total_tool_calls,
            "trigger_events": trigger_events,
            "tool_calls": tool_calls,
            "timestamp": time.time(),
        })

    async def _flush(self):
        if not self._buffer:
            return

        batch = self._buffer[:]
        self._buffer.clear()

        sensors = [e for e in batch if e["type"] in ("sensor", "event")]
        decisions = [e for e in batch if e["type"] == "decision"]

        table_prefix = "events." if IS_POSTGRES else ""

        try:
            async with self._engine.begin() as conn:
                if sensors:
                    for s in sensors:
                        await conn.execute(
                            text(f"INSERT INTO {table_prefix}raw_events (zone, event_type, data) VALUES (:zone, :event_type, :data)"),
                            {"zone": s["zone"], "event_type": s["event_type"], "data": json.dumps(s["data"])},
                        )

                if decisions:
                    for d in decisions:
                        await conn.execute(
                            text(f"INSERT INTO {table_prefix}llm_decisions (cycle_duration, iterations, total_tool_calls, trigger_events, tool_calls) VALUES (:dur, :iter, :tc, :te, :tcs)"),
                            {
                                "dur": d["cycle_duration"],
                                "iter": d["iterations"],
                                "tc": d["total_tool_calls"],
                                "te": json.dumps(d["trigger_events"]),
                                "tcs": json.dumps(d["tool_calls"]),
                            },
                        )

            logger.debug(f"Flushed {len(sensors)} events + {len(decisions)} decisions")
        except Exception as e:
            logger.error(f"Event flush failed: {e}")
            # Re-queue on failure
            self._buffer = batch + self._buffer
