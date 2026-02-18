"""
EventWriter: Async buffered writer for sensor telemetry and LLM decisions.

Buffers events in-memory and flushes to PostgreSQL every 5 seconds via
bulk INSERT. The MQTT callback thread calls record_*() methods, which
only append to a list; the flush loop runs on the asyncio event loop.
"""
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


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
            "timestamp": datetime.now(timezone.utc),
            "zone": zone,
            "event_type": "sensor_reading",
            "source_device": device_id,
            "data": json.dumps({
                "channel": channel,
                "value": value,
                "topic": topic,
            }),
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
            "timestamp": datetime.now(timezone.utc),
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
            "timestamp": datetime.now(timezone.utc),
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

        async with self._engine.begin() as conn:
            if events:
                await conn.execute(
                    text("""
                        INSERT INTO events.raw_events
                            (timestamp, zone, event_type, source_device, data)
                        VALUES
                            (:timestamp, :zone, :event_type, :source_device, CAST(:data AS jsonb))
                    """),
                    events,
                )
                logger.debug("Flushed {} raw events", len(events))

            if decisions:
                await conn.execute(
                    text("""
                        INSERT INTO events.llm_decisions
                            (timestamp, cycle_duration_sec, iterations,
                             total_tool_calls, trigger_events, tool_calls,
                             world_state_snapshot)
                        VALUES
                            (:timestamp, :cycle_duration_sec, :iterations,
                             :total_tool_calls, CAST(:trigger_events AS jsonb),
                             CAST(:tool_calls AS jsonb), CAST(:world_state_snapshot AS jsonb))
                    """),
                    decisions,
                )
                logger.debug("Flushed {} LLM decisions", len(decisions))
