"""
EventWriter: Async buffered writer for sensor telemetry and LLM decisions.
SQLite and PostgreSQL compatible.

Buffers events in-memory and flushes to the database every 5 seconds.
The MQTT callback thread calls record_*() methods, which only append to
a list; the flush loop runs on the asyncio event loop. An asyncio.Lock
guards buffer access to prevent races during flush.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

IS_POSTGRES = "postgresql" in os.getenv("DATABASE_URL", "")


class EventWriter:
    FLUSH_INTERVAL = 5  # seconds

    def __init__(self, engine: AsyncEngine):
        self._engine = engine
        self._events: list[dict] = []
        self._decisions: list[dict] = []
        self._lock = asyncio.Lock()
        self._running = False

    # ------------------------------------------------------------------
    # Public record methods (called from MQTT thread via call_soon_threadsafe
    # or directly from asyncio coroutines)
    # ------------------------------------------------------------------

    def record_sensor(
        self,
        zone: str,
        channel: str,
        value: Any,
        device_id: str | None = None,
        topic: str | None = None,
    ):
        """Buffer a sensor reading as a raw_event."""
        self._events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone": zone,
            "event_type": "sensor_reading",
            "source_device": device_id,
            "data": json.dumps({
                "channel": channel,
                "value": value,
                "topic": topic,
            }),
        })

    def record_event(self, zone: str, event_type: str, data: dict = None):
        """Buffer a generic event as a raw_event."""
        self._events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone": zone,
            "event_type": event_type,
            "source_device": None,
            "data": json.dumps(data or {}),
        })

    def record_world_event(
        self,
        zone: str,
        event_type: str,
        severity: str,
        data: dict,
    ):
        """Buffer a WorldModel event (person_entered, co2_threshold, etc.)."""
        self._events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone": zone,
            "event_type": f"world_model_{event_type}",
            "source_device": None,
            "data": json.dumps({"severity": severity, **data}),
        })

    def record_decision(
        self,
        cycle_duration: float,
        iterations: int,
        total_tool_calls: int,
        trigger_events: list | None = None,
        tool_calls: list | None = None,
        world_state_snapshot: dict | None = None,
    ):
        """Buffer an LLM cognitive cycle decision."""
        self._decisions.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cycle_duration_sec": cycle_duration,
            "iterations": iterations,
            "total_tool_calls": total_tool_calls,
            "trigger_events": json.dumps(trigger_events or []),
            "tool_calls": json.dumps(tool_calls or []),
            "world_state_snapshot": json.dumps(world_state_snapshot or {}),
        })

    # ------------------------------------------------------------------
    # Flush loop
    # ------------------------------------------------------------------

    async def start(self):
        """Start the background flush loop."""
        self._running = True
        logger.info("EventWriter started (flush every {}s)", self.FLUSH_INTERVAL)
        while self._running:
            await asyncio.sleep(self.FLUSH_INTERVAL)
            try:
                await self._flush()
            except Exception as e:
                logger.error("EventWriter flush error: {}", e)

    async def stop(self):
        """Stop the flush loop and do a final flush."""
        self._running = False
        await self._flush()
        logger.info("EventWriter stopped")

    async def _flush(self):
        """Bulk INSERT buffered events and decisions, then clear buffers."""
        async with self._lock:
            events = self._events[:]
            decisions = self._decisions[:]
            self._events.clear()
            self._decisions.clear()

        if not events and not decisions:
            return

        tp = "events." if IS_POSTGRES else ""

        try:
            async with self._engine.begin() as conn:
                if events:
                    if IS_POSTGRES:
                        await conn.execute(
                            text(f"""
                                INSERT INTO {tp}raw_events
                                    (timestamp, zone, event_type, source_device, data)
                                VALUES
                                    (:timestamp, :zone, :event_type, :source_device,
                                     CAST(:data AS jsonb))
                            """),
                            events,
                        )
                    else:
                        for e in events:
                            await conn.execute(
                                text(f"""
                                    INSERT INTO {tp}raw_events
                                        (timestamp, zone, event_type, source_device, data)
                                    VALUES (:timestamp, :zone, :event_type, :source_device, :data)
                                """),
                                e,
                            )
                    logger.debug("Flushed {} raw events", len(events))

                if decisions:
                    if IS_POSTGRES:
                        await conn.execute(
                            text(f"""
                                INSERT INTO {tp}llm_decisions
                                    (timestamp, cycle_duration_sec, iterations,
                                     total_tool_calls, trigger_events, tool_calls,
                                     world_state_snapshot)
                                VALUES
                                    (:timestamp, :cycle_duration_sec, :iterations,
                                     :total_tool_calls, CAST(:trigger_events AS jsonb),
                                     CAST(:tool_calls AS jsonb),
                                     CAST(:world_state_snapshot AS jsonb))
                            """),
                            decisions,
                        )
                    else:
                        for d in decisions:
                            await conn.execute(
                                text(f"""
                                    INSERT INTO {tp}llm_decisions
                                        (timestamp, cycle_duration_sec, iterations,
                                         total_tool_calls, trigger_events, tool_calls,
                                         world_state_snapshot)
                                    VALUES
                                        (:timestamp, :cycle_duration_sec, :iterations,
                                         :total_tool_calls, :trigger_events, :tool_calls,
                                         :world_state_snapshot)
                                """),
                                d,
                            )
                    logger.debug("Flushed {} LLM decisions", len(decisions))

        except Exception as e:
            logger.error("Event flush failed: {}", e)
            # Re-queue on failure so data is not lost
            async with self._lock:
                self._events = events + self._events
                self._decisions = decisions + self._decisions
