"""Durable canonical biometric intake; delivery workers are intentionally out of scope."""

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from hems_common.biometric import BiometricObservationIn, canonical_observation_payload

_SCHEMA_NAME = "canonical_observation_store"
_SCHEMA_VERSION = 1
_BACKEND_TARGET = "/internal/biometric/observations"

_INIT_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS observation_inbox (
        observation_id TEXT PRIMARY KEY,
        canonical_hash TEXT NOT NULL,
        canonical_json TEXT NOT NULL,
        received_at TEXT NOT NULL,
        status TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS delivery_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observation_id TEXT NOT NULL REFERENCES observation_inbox(observation_id),
        destination TEXT NOT NULL CHECK(destination IN ('mqtt', 'backend')),
        target TEXT NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        next_attempt_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(observation_id, destination, target)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_delivery_outbox_due ON delivery_outbox(status, next_attempt_at, created_at)",
)


class ObservationConflictError(Exception):
    """The stable observation ID was reused for different canonical content."""


class ObservationStoreError(Exception):
    """The durable intake transaction could not be completed."""


@dataclass(frozen=True)
class MqttDelivery:
    topic: str
    payload: dict


def _metadata(data: BiometricObservationIn) -> dict:
    payload, _ = canonical_observation_payload(data)
    return {key: value for key, value in payload.items() if key != "metrics"}


def map_observation_to_mqtt(
    data: BiometricObservationIn, topic_prefix: str = "hems/personal/biometrics"
) -> list[MqttDelivery]:
    """Map one canonical observation to retained-compatible metric envelopes."""
    metadata = _metadata(data)
    metrics = data.metrics.model_dump(exclude_none=True)
    grouped: dict[str, dict] = {}

    def add(topic_metric: str, legacy_key: str, value) -> None:
        envelope = grouped.setdefault(topic_metric, {**metadata, "metric": topic_metric})
        envelope[legacy_key] = value

    if "heart_rate" in metrics:
        add("heart_rate", "bpm", metrics["heart_rate"])
    if "resting_heart_rate" in metrics:
        add("heart_rate", "resting_bpm", metrics["resting_heart_rate"])
    if "spo2" in metrics:
        add("spo2", "percent", metrics["spo2"])
    if "steps" in metrics:
        add("steps", "count", metrics["steps"])
    if "calories" in metrics:
        add("activity", "calories", metrics["calories"])
    if "active_minutes" in metrics:
        add("activity", "active_minutes", metrics["active_minutes"])
    if "stress_level" in metrics:
        add("stress", "level", metrics["stress_level"])
    if "fatigue_score" in metrics:
        add("fatigue", "score", metrics["fatigue_score"])
    if "sleep_duration_minutes" in metrics:
        add("sleep", "duration_minutes", metrics["sleep_duration_minutes"])
    if "sleep_quality_score" in metrics:
        add("sleep", "quality_score", metrics["sleep_quality_score"])
    if "hrv_ms" in metrics:
        add("hrv", "rmssd_ms", metrics["hrv_ms"])
    if "body_temperature" in metrics:
        add("body_temperature", "celsius", metrics["body_temperature"])
    if "respiratory_rate" in metrics:
        add("respiratory_rate", "breaths_per_minute", metrics["respiratory_rate"])

    prefix = f"{topic_prefix.rstrip('/')}/{data.provider}"
    return [MqttDelivery(topic=f"{prefix}/{metric}", payload=payload) for metric, payload in grouped.items()]


class CanonicalObservationStore:
    """Owns canonical inbox/outbox tables alongside, but separate from, legacy send_queue.outbox."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv("BIOMETRIC_DB_PATH", "/data/send_queue.db")
        self._initialized = False

    async def init(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_sync()
        self._initialized = True

    def _init_sync(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as db:
                db.execute("PRAGMA foreign_keys = ON")
                db.execute(
                    "CREATE TABLE IF NOT EXISTS biometric_schema_versions "
                    "(name TEXT PRIMARY KEY, version INTEGER NOT NULL)"
                )
                row = db.execute(
                    "SELECT version FROM biometric_schema_versions WHERE name = ?", (_SCHEMA_NAME,)
                ).fetchone()
                version = row[0] if row else 0
                if version > _SCHEMA_VERSION:
                    raise ObservationStoreError(f"unsupported canonical store schema version: {version}")
                if version == _SCHEMA_VERSION:
                    return
                db.execute("BEGIN IMMEDIATE")
                for statement in _INIT_STATEMENTS:
                    db.execute(statement)
                db.execute(
                    "INSERT INTO biometric_schema_versions (name, version) VALUES (?, ?)",
                    (_SCHEMA_NAME, _SCHEMA_VERSION),
                )
        except sqlite3.Error as exc:
            raise ObservationStoreError("canonical biometric schema initialization failed") from exc

    async def close(self) -> None:
        self._initialized = False

    async def ingest(self, data: BiometricObservationIn) -> bool:
        """Atomically create inbox and all delivery rows; return True for a duplicate."""
        if not self._initialized:
            raise ObservationStoreError("canonical observation store is not initialized")
        return self._ingest_sync(data)

    def _ingest_sync(self, data: BiometricObservationIn) -> bool:
        canonical, canonical_hash = canonical_observation_payload(data)
        canonical_json = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        now = datetime.now(UTC).isoformat()
        try:
            with sqlite3.connect(self.db_path) as db:
                db.execute("PRAGMA foreign_keys = ON")
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute(
                    "SELECT canonical_hash FROM observation_inbox WHERE observation_id = ?",
                    (data.observation_id,),
                ).fetchone()
                if existing:
                    if existing[0] == canonical_hash:
                        return True
                    raise ObservationConflictError(data.observation_id)

                db.execute(
                    """INSERT INTO observation_inbox
                       (observation_id, canonical_hash, canonical_json, received_at, status)
                       VALUES (?, ?, ?, ?, 'pending_delivery')""",
                    (data.observation_id, canonical_hash, canonical_json, now),
                )
                deliveries = map_observation_to_mqtt(data)
                deliveries.append(MqttDelivery(topic=_BACKEND_TARGET, payload=canonical))
                for delivery in deliveries:
                    destination = "backend" if delivery.topic == _BACKEND_TARGET else "mqtt"
                    db.execute(
                        """INSERT INTO delivery_outbox
                           (observation_id, destination, target, payload, status, attempts, created_at, updated_at)
                           VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)""",
                        (
                            data.observation_id,
                            destination,
                            delivery.topic,
                            json.dumps(delivery.payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                            now,
                            now,
                        ),
                    )
                return False
        except ObservationConflictError:
            raise
        except sqlite3.Error as exc:
            raise ObservationStoreError("canonical biometric intake transaction failed") from exc
