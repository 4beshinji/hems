"""
EventWriter: Async buffered writer for sensor telemetry and LLM decisions.
SQLite and PostgreSQL compatible.

Buffers events in-memory and flushes to the database every 5 seconds.
The MQTT callback thread calls record_*() methods, which only append to
a list; the flush loop runs on the asyncio event loop. An asyncio.Lock
guards buffer access to prevent races during flush.
"""

import asyncio
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

IS_POSTGRES = "postgresql" in os.getenv("DATABASE_URL", "")


class EventWriter:
    FLUSH_INTERVAL = 5  # seconds

    # 5-minute dedupe window for world events (shopping/gas/weather/news)
    WORLD_EVENT_DEDUPE_SECONDS = 300

    def __init__(self, engine: AsyncEngine):
        self._engine = engine
        self._events: list[dict] = []
        self._decisions: list[dict] = []
        self._world_events: list[dict] = []
        # payload_digest → last accepted timestamp (unix); for 5min dedupe
        self._world_dedup: dict[str, float] = {}
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
        self._events.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "zone": zone,
                "event_type": "sensor_reading",
                "source_device": device_id,
                "data": json.dumps(
                    {
                        "channel": channel,
                        "value": value,
                        "topic": topic,
                    }
                ),
            }
        )

    def record_event(self, zone: str, event_type: str, data: dict = None):
        """Buffer a generic event as a raw_event."""
        self._events.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "zone": zone,
                "event_type": event_type,
                "source_device": None,
                "data": json.dumps(data or {}),
            }
        )

    def record_world_event(
        self,
        source_type: str,
        topic: str,
        payload: Any,
        subject_ref: str | None = None,
    ) -> bool:
        """Buffer a world event (shopping/gas/weather_alert/news_urgent/...).

        Deduplicates on payload_digest with a 5-minute cooldown so retained
        MQTT messages and repeat polls do not bloat the store.

        Returns True if the event was accepted (and buffered), False if
        suppressed by the dedupe window.
        """
        try:
            payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            payload_json = json.dumps({"repr": str(payload)[:500]}, ensure_ascii=False)

        digest = hashlib.sha1(
            f"{source_type}|{topic}|{subject_ref or ''}|{payload_json}".encode("utf-8", errors="replace")
        ).hexdigest()[:20]

        now = time.time()
        last = self._world_dedup.get(digest, 0.0)
        if now - last < self.WORLD_EVENT_DEDUPE_SECONDS:
            return False

        self._world_dedup[digest] = now
        # Opportunistic cleanup: prune old dedup entries when map grows
        if len(self._world_dedup) > 512:
            cutoff = now - self.WORLD_EVENT_DEDUPE_SECONDS
            self._world_dedup = {k: v for k, v in self._world_dedup.items() if v >= cutoff}

        self._world_events.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "source_type": source_type,
                "topic": topic,
                "payload_digest": digest,
                "subject_ref": subject_ref,
                "data": payload_json,
            }
        )
        return True

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
        self._decisions.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "cycle_duration_sec": cycle_duration,
                "iterations": iterations,
                "total_tool_calls": total_tool_calls,
                "trigger_events": json.dumps(trigger_events or []),
                "tool_calls": json.dumps(tool_calls or []),
                "world_state_snapshot": json.dumps(world_state_snapshot or {}),
            }
        )

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
            world_events = self._world_events[:]
            self._events.clear()
            self._decisions.clear()
            self._world_events.clear()

        if not events and not decisions and not world_events:
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

                if world_events:
                    if IS_POSTGRES:
                        await conn.execute(
                            text(f"""
                                INSERT INTO {tp}world_events
                                    (timestamp, source_type, topic, payload_digest,
                                     subject_ref, data)
                                VALUES
                                    (:timestamp, :source_type, :topic, :payload_digest,
                                     :subject_ref, CAST(:data AS jsonb))
                            """),
                            world_events,
                        )
                    else:
                        for w in world_events:
                            await conn.execute(
                                text(f"""
                                    INSERT INTO {tp}world_events
                                        (timestamp, source_type, topic, payload_digest,
                                         subject_ref, data)
                                    VALUES (:timestamp, :source_type, :topic,
                                            :payload_digest, :subject_ref, :data)
                                """),
                                w,
                            )
                    logger.debug("Flushed {} world events", len(world_events))

        except Exception as e:
            logger.error("Event flush failed: {}", e)
            # Re-queue on failure so data is not lost
            async with self._lock:
                self._events = events + self._events
                self._decisions = decisions + self._decisions
                self._world_events = world_events + self._world_events
