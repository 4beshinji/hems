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
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

IS_POSTGRES = "postgresql" in os.getenv("DATABASE_URL", "")
# Schema-qualified table prefix: Postgres groups the data-mart tables under the
# `events` schema; SQLite keeps them in the default schema.
TABLE_PREFIX = "events." if IS_POSTGRES else ""


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
        # Intervention efficacy (Group D): created rows are INSERTed, completed
        # rows are UPDATEd by task_id. Buffered like everything else so the
        # MQTT-thread completion path stays a plain thread-safe append.
        self._interventions_created: list[dict] = []
        self._interventions_completed: list[dict] = []
        self._interventions_updates: list[dict] = []
        self._agent_feedback: list[dict] = []
        self._agent_trajectories: list[dict] = []
        self._drift_detections: list[dict] = []
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
        cause_event_id: int | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        gpu_util_pct: float | None = None,
        gpu_power_w: float | None = None,
    ):
        """Buffer an LLM cognitive cycle decision.

        cause_event_id: optional FK back to world_events.id — the originating
        event that triggered this cognitive cycle (e.g. a GAS event change,
        biometric threshold crossing). Enables causal traceability.

        prompt_tokens/completion_tokens/gpu_util_pct/gpu_power_w: optional
        cost/energy metering (Group E). All nullable — rule-based cycles and
        backends that report no usage leave them None.
        """
        self._decisions.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "cycle_duration_sec": cycle_duration,
                "iterations": iterations,
                "total_tool_calls": total_tool_calls,
                "trigger_events": json.dumps(trigger_events or []),
                "tool_calls": json.dumps(tool_calls or []),
                "world_state_snapshot": json.dumps(world_state_snapshot or {}),
                "cause_event_id": cause_event_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "gpu_util_pct": gpu_util_pct,
                "gpu_power_w": gpu_power_w,
            }
        )

    # ------------------------------------------------------------------
    # Intervention efficacy (Group D)
    # ------------------------------------------------------------------

    def record_intervention_created(
        self,
        task_id: str,
        zone: str,
        trigger_metric: str,
        baseline_value: float | None,
        window_sec: int = 1800,
        approval_id: str | None = None,
    ):
        """Buffer a pending efficacy row for an environment task (INSERT).

        approval_id links the intervention to a HITL approval request so the
        human decision and rollback state can be correlated with efficacy.
        """
        self._interventions_created.append(
            {
                "task_id": str(task_id),
                "zone": zone,
                "trigger_metric": trigger_metric,
                "baseline_value": baseline_value,
                "created_at": datetime.now(UTC).isoformat(),
                "window_sec": window_sec,
                "approval_id": approval_id,
            }
        )

    def mark_intervention_completed(self, task_id: str):
        """Buffer a completion timestamp for a tracked task (UPDATE by task_id).

        Safe to call from the MQTT-dispatch thread — only appends.
        """
        self._interventions_completed.append({"task_id": str(task_id), "completed_at": datetime.now(UTC).isoformat()})

    def record_intervention_decision(self, approval_id: str, human_decision: str):
        """Buffer a human decision for the efficacy row tied to an approval_id."""
        self._interventions_updates.append(
            {
                "approval_id": approval_id,
                "human_decision": human_decision,
                "decided_at": datetime.now(UTC).isoformat(),
            }
        )

    def record_intervention_rollback(
        self,
        approval_id: str,
        rolled_back: bool,
        rollback_success: bool | None,
    ):
        """Buffer rollback state for the efficacy row tied to an approval_id."""
        if rolled_back:
            rb_success_val = 1 if rollback_success is True else 0 if rollback_success is False else None
        else:
            rb_success_val = 0
        self._interventions_updates.append(
            {
                "approval_id": approval_id,
                "rolled_back": 1 if rolled_back else 0,
                "rollback_success": rb_success_val,
                "rolled_back_at": datetime.now(UTC).isoformat(),
            }
        )

    # ------------------------------------------------------------------
    # Phase 1: agent feedback and learning trajectories
    # ------------------------------------------------------------------

    def record_feedback(
        self,
        target_type: str,
        target_id: str,
        feedback_type: str,
        channel: str = "mqtt",
        payload: dict | None = None,
        context: dict | None = None,
        user_id: str | None = None,
    ):
        """Buffer a normalized agent feedback row."""
        self._agent_feedback.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "feedback_type": feedback_type,
                "channel": channel,
                "payload": json.dumps(payload or {}, ensure_ascii=False, default=str),
                "context": json.dumps(context or {}, ensure_ascii=False, default=str),
                "user_id": user_id,
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        )

    def record_trajectory(
        self,
        cycle_id: str | None,
        decision_id: str | None,
        trigger_events: list | None,
        tool_calls: list | None,
        world_state_snapshot: dict | None,
        outcome_summary: dict | None,
    ):
        """Buffer a decision-to-outcome trajectory row."""
        self._agent_trajectories.append(
            {
                "cycle_id": cycle_id,
                "decision_id": decision_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "trigger_events": json.dumps(trigger_events or [], ensure_ascii=False, default=str),
                "tool_calls": json.dumps(tool_calls or [], ensure_ascii=False, default=str),
                "world_state_snapshot": json.dumps(world_state_snapshot or {}, ensure_ascii=False, default=str),
                "outcome_summary": json.dumps(outcome_summary or {}, ensure_ascii=False, default=str),
            }
        )

    def record_drift_detection(
        self,
        metric_key: str,
        detector: str,
        old_threshold: float | None,
        proposed_threshold: float | None,
        detector_state: dict | None = None,
    ):
        """Buffer a drift detection event for observability and later learning."""
        self._drift_detections.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "metric_key": metric_key,
                "detector": detector,
                "old_threshold": old_threshold,
                "proposed_threshold": proposed_threshold,
                "detector_state": json.dumps(detector_state or {}, ensure_ascii=False, default=str),
            }
        )

    async def fetch_pending_interventions(self) -> list[dict]:
        """Return completed-but-unverdicted rows whose post-window has elapsed.

        Window elapsis is computed in Python so the query stays backend-agnostic
        (SQLite has no interval arithmetic).
        """
        tp = TABLE_PREFIX
        async with self._engine.begin() as conn:
            rows = await conn.execute(
                text(f"""
                    SELECT id, task_id, zone, trigger_metric, baseline_value,
                           completed_at, window_sec, approval_id, human_decision,
                           rolled_back, rollback_success, efficacy_score
                    FROM {tp}intervention_efficacy
                    WHERE verdict IS NULL AND completed_at IS NOT NULL
                    ORDER BY completed_at
                    LIMIT 50
                """)
            )
            now = datetime.now(UTC)
            pending = []
            for r in rows:
                d = dict(r._mapping)
                ca = d["completed_at"]
                if isinstance(ca, str):
                    ca = datetime.fromisoformat(ca)
                if ca.tzinfo is None:
                    ca = ca.replace(tzinfo=UTC)
                if now >= ca + timedelta(seconds=d["window_sec"]):
                    pending.append(d)
            return pending

    async def compute_post_value(self, zone: str, channel: str, start, window_sec: int) -> float | None:
        """AVG of a channel's sensor readings in [start, start+window_sec)."""
        if isinstance(start, str):
            start_dt = datetime.fromisoformat(start)
        else:
            start_dt = start
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=UTC)
        start_str = start_dt.isoformat()
        end_str = (start_dt + timedelta(seconds=window_sec)).isoformat()
        tp = TABLE_PREFIX
        async with self._engine.begin() as conn:
            if IS_POSTGRES:
                row = await conn.execute(
                    text(rf"""
                        SELECT AVG((data->>'value')::float)
                        FROM {tp}raw_events
                        WHERE zone = :zone AND event_type = 'sensor_reading'
                          AND data->>'channel' = :channel
                          AND timestamp >= :start AND timestamp < :end
                          AND data->>'value' ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                    """),
                    {"zone": zone, "channel": channel, "start": start_str, "end": end_str},
                )
            else:
                row = await conn.execute(
                    text("""
                        SELECT AVG(CAST(json_extract(data, '$.value') AS REAL))
                        FROM raw_events
                        WHERE zone = :zone AND event_type = 'sensor_reading'
                          AND json_extract(data, '$.channel') = :channel
                          AND timestamp >= :start AND timestamp < :end
                          AND typeof(json_extract(data, '$.value')) IN ('integer', 'real')
                    """),
                    {"zone": zone, "channel": channel, "start": start_str, "end": end_str},
                )
            return row.scalar()

    async def record_intervention_verdict(
        self,
        row_id: int,
        post_value: float | None,
        verdict: str,
        efficacy_score: float | None = None,
    ):
        """Persist the post value + verdict (+ optional score) for one efficacy row (UPDATE)."""
        tp = TABLE_PREFIX
        now_str = datetime.now(UTC).isoformat()
        async with self._engine.begin() as conn:
            await conn.execute(
                text(f"""
                    UPDATE {tp}intervention_efficacy
                    SET post_value = :post_value,
                        verdict = :verdict,
                        evaluated_at = :evaluated_at,
                        efficacy_score = :efficacy_score
                    WHERE id = :row_id
                """),
                {
                    "row_id": row_id,
                    "post_value": post_value,
                    "verdict": verdict,
                    "evaluated_at": now_str,
                    "efficacy_score": efficacy_score,
                },
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

    async def _bulk_insert(self, conn, table: str, cols: list[str], rows: list[dict], jsonb_cols: tuple = ()):
        """INSERT rows into {TABLE_PREFIX}{table}.

        On Postgres the columns in *jsonb_cols* are CAST to jsonb and all rows
        go in a single executemany; on SQLite each row is inserted plainly
        (jsonb_cols are stored as-is, matching the legacy per-row path).
        """
        col_list = ", ".join(cols)
        if IS_POSTGRES:
            values = ", ".join(f"CAST(:{c} AS jsonb)" if c in jsonb_cols else f":{c}" for c in cols)
            await conn.execute(
                text(f"INSERT INTO {TABLE_PREFIX}{table} ({col_list}) VALUES ({values})"),
                rows,
            )
        else:
            values = ", ".join(f":{c}" for c in cols)
            stmt = text(f"INSERT INTO {TABLE_PREFIX}{table} ({col_list}) VALUES ({values})")
            for r in rows:
                await conn.execute(stmt, r)

    async def _flush(self):
        """Bulk INSERT buffered events and decisions, then clear buffers."""
        async with self._lock:
            events = self._events[:]
            decisions = self._decisions[:]
            world_events = self._world_events[:]
            iv_created = self._interventions_created[:]
            iv_completed = self._interventions_completed[:]
            iv_updates = self._interventions_updates[:]
            feedback_rows = self._agent_feedback[:]
            trajectories = self._agent_trajectories[:]
            drift_detections = self._drift_detections[:]
            self._events.clear()
            self._decisions.clear()
            self._world_events.clear()
            self._interventions_created.clear()
            self._interventions_completed.clear()
            self._interventions_updates.clear()
            self._agent_feedback.clear()
            self._agent_trajectories.clear()
            self._drift_detections.clear()

        if (
            not events
            and not decisions
            and not world_events
            and not iv_created
            and not iv_completed
            and not iv_updates
            and not feedback_rows
            and not trajectories
            and not drift_detections
        ):
            return

        tp = TABLE_PREFIX

        try:
            async with self._engine.begin() as conn:
                if events:
                    await self._bulk_insert(
                        conn,
                        "raw_events",
                        ["timestamp", "zone", "event_type", "source_device", "data"],
                        events,
                        jsonb_cols=("data",),
                    )
                    logger.debug("Flushed {} raw events", len(events))

                if decisions:
                    # Ensure newer columns are present (default None) for buffers
                    # captured before a code update — backward compatibility.
                    for d in decisions:
                        d.setdefault("cause_event_id", None)
                        d.setdefault("prompt_tokens", None)
                        d.setdefault("completion_tokens", None)
                        d.setdefault("gpu_util_pct", None)
                        d.setdefault("gpu_power_w", None)
                    await self._bulk_insert(
                        conn,
                        "llm_decisions",
                        [
                            "timestamp",
                            "cycle_duration_sec",
                            "iterations",
                            "total_tool_calls",
                            "trigger_events",
                            "tool_calls",
                            "world_state_snapshot",
                            "cause_event_id",
                            "prompt_tokens",
                            "completion_tokens",
                            "gpu_util_pct",
                            "gpu_power_w",
                        ],
                        decisions,
                        jsonb_cols=("trigger_events", "tool_calls", "world_state_snapshot"),
                    )
                    logger.debug("Flushed {} LLM decisions", len(decisions))

                if world_events:
                    await self._bulk_insert(
                        conn,
                        "world_events",
                        ["timestamp", "source_type", "topic", "payload_digest", "subject_ref", "data"],
                        world_events,
                        jsonb_cols=("data",),
                    )
                    logger.debug("Flushed {} world events", len(world_events))

                if iv_created:
                    await self._bulk_insert(
                        conn,
                        "intervention_efficacy",
                        [
                            "task_id",
                            "zone",
                            "trigger_metric",
                            "baseline_value",
                            "created_at",
                            "window_sec",
                            "approval_id",
                        ],
                        iv_created,
                    )
                    logger.debug("Flushed {} intervention rows", len(iv_created))

                if iv_completed:
                    # UPDATE the latest still-open row for each task_id.
                    for iv in iv_completed:
                        await conn.execute(
                            text(f"""
                                UPDATE {tp}intervention_efficacy
                                SET completed_at = :completed_at
                                WHERE task_id = :task_id AND completed_at IS NULL
                            """),
                            iv,
                        )
                    logger.debug("Flushed {} intervention completions", len(iv_completed))

                if iv_updates:
                    # UPDATE the latest row for each approval_id.
                    for iv in iv_updates:
                        fields = []
                        params = {"approval_id": iv["approval_id"]}
                        for col in ("human_decision", "rolled_back", "rollback_success"):
                            if col in iv:
                                fields.append(f"{col} = :{col}")
                                params[col] = iv[col]
                        if not fields:
                            continue
                        # Backend-agnostic "latest row for approval_id" update.
                        row = await conn.execute(
                            text(f"""
                                SELECT id FROM {tp}intervention_efficacy
                                WHERE approval_id = :approval_id
                                ORDER BY created_at DESC
                                LIMIT 1
                            """),
                            {"approval_id": iv["approval_id"]},
                        )
                        latest = row.scalar()
                        if latest is not None:
                            await conn.execute(
                                text(f"""
                                    UPDATE {tp}intervention_efficacy
                                    SET {", ".join(fields)}
                                    WHERE id = :row_id
                                """),
                                {**params, "row_id": latest},
                            )
                    logger.debug("Flushed {} intervention approval updates", len(iv_updates))

                if feedback_rows:
                    await self._bulk_insert(
                        conn,
                        "agent_feedback",
                        [
                            "target_type",
                            "target_id",
                            "feedback_type",
                            "channel",
                            "payload",
                            "context",
                            "user_id",
                            "recorded_at",
                        ],
                        feedback_rows,
                        jsonb_cols=("payload", "context"),
                    )
                    logger.debug("Flushed {} agent feedback rows", len(feedback_rows))

                if trajectories:
                    await self._bulk_insert(
                        conn,
                        "agent_trajectories",
                        [
                            "cycle_id",
                            "decision_id",
                            "timestamp",
                            "trigger_events",
                            "tool_calls",
                            "world_state_snapshot",
                            "outcome_summary",
                        ],
                        trajectories,
                        jsonb_cols=("trigger_events", "tool_calls", "world_state_snapshot", "outcome_summary"),
                    )
                    logger.debug("Flushed {} agent trajectories", len(trajectories))

                if drift_detections:
                    await self._bulk_insert(
                        conn,
                        "drift_detections",
                        [
                            "timestamp",
                            "metric_key",
                            "detector",
                            "old_threshold",
                            "proposed_threshold",
                            "detector_state",
                        ],
                        drift_detections,
                        jsonb_cols=("detector_state",),
                    )
                    logger.debug("Flushed {} drift detections", len(drift_detections))

        except Exception as e:
            logger.error("Event flush failed: {}", e)
            # Re-queue on failure so data is not lost
            async with self._lock:
                self._events = events + self._events
                self._decisions = decisions + self._decisions
                self._world_events = world_events + self._world_events
                self._interventions_created = iv_created + self._interventions_created
                self._interventions_completed = iv_completed + self._interventions_completed
                self._interventions_updates = iv_updates + self._interventions_updates
                self._agent_feedback = feedback_rows + self._agent_feedback
                self._agent_trajectories = trajectories + self._agent_trajectories
                self._drift_detections = drift_detections + self._drift_detections
