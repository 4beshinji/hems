"""Focused P1.2a canonical biometric bridge intake tests."""

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_ROOT = Path(__file__).resolve().parent.parent
_BRIDGE_SRC = _ROOT / "services" / "biometric-bridge" / "src"
sys.path.insert(0, str(_BRIDGE_SRC))

from canonical_ingest import (
    _INIT_STATEMENTS,
    CanonicalObservationStore,
    ObservationConflictError,
    ObservationStoreError,
    map_observation_to_mqtt,
)

from hems_common.auth import verify_internal_token
from hems_common.biometric import BiometricObservationIn as CommonObservation
from schemas import BiometricObservationIn as BackendObservation


def _observation(**overrides) -> CommonObservation:
    payload = {
        "schema_version": 1,
        "observation_id": "healthconnect:batch:20260719T020304Z",
        "provider": "healthconnect",
        "device_id": "mobile.pixel_9",
        "source_ts": "2026-07-19T11:03:04+09:00",
        "interval_start": "2026-07-19T02:00:00Z",
        "interval_end": "2026-07-19T02:05:00Z",
        "aggregation": "sample",
        "metrics": {"heart_rate": 73, "resting_heart_rate": 58, "spo2": 98, "steps": 4321},
    }
    payload.update(overrides)
    return CommonObservation.model_validate(payload)


def test_backend_reexports_the_common_observation_contract():
    assert BackendObservation is CommonObservation


def test_store_upgrades_existing_v1_schema(tmp_path):
    db_path = tmp_path / "v1.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE biometric_schema_versions (name TEXT PRIMARY KEY, version INTEGER NOT NULL)")
        for statement in _INIT_STATEMENTS:
            connection.execute(statement)
        connection.execute("INSERT INTO biometric_schema_versions VALUES ('canonical_observation_store', 1)")

    store = CanonicalObservationStore(str(db_path))
    asyncio.run(store.init())
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT version FROM biometric_schema_versions WHERE name = 'canonical_observation_store'"
        ).fetchone() == (2,)
        assert "lease_until" in {row[1] for row in connection.execute("PRAGMA table_info(delivery_outbox)")}


def test_mqtt_mapper_preserves_metadata_and_legacy_metric_keys():
    deliveries = {delivery.topic: delivery.payload for delivery in map_observation_to_mqtt(_observation())}

    heart_rate = deliveries["hems/personal/biometrics/healthconnect/heart_rate"]
    assert heart_rate["schema_version"] == 1
    assert heart_rate["observation_id"] == "healthconnect:batch:20260719T020304Z"
    assert heart_rate["provider"] == "healthconnect"
    assert heart_rate["device_id"] == "mobile.pixel_9"
    assert heart_rate["source_ts"] == "2026-07-19T02:03:04Z"
    assert heart_rate["aggregation"] == "sample"
    assert heart_rate["metric"] == "heart_rate"
    assert heart_rate["bpm"] == 73
    assert heart_rate["resting_bpm"] == 58
    assert deliveries["hems/personal/biometrics/healthconnect/spo2"]["percent"] == 98
    assert deliveries["hems/personal/biometrics/healthconnect/steps"]["count"] == 4321


def test_ingest_transaction_is_idempotent_and_preserves_legacy_queue(tmp_path):
    db_path = tmp_path / "send_queue.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """CREATE TABLE outbox (
               id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, payload TEXT NOT NULL,
               retain INTEGER DEFAULT 0, created_at REAL NOT NULL, attempts INTEGER DEFAULT 0)"""
        )
        connection.execute(
            "INSERT INTO outbox (topic, payload, retain, created_at) VALUES (?, ?, ?, ?)",
            ("legacy/topic", '{"value":1}', 1, 1.0),
        )

    store = CanonicalObservationStore(str(db_path))
    asyncio.run(store.init())
    observation = _observation()
    assert asyncio.run(store.ingest(observation)) is False
    assert asyncio.run(store.ingest(observation)) is True
    with pytest.raises(ObservationConflictError):
        asyncio.run(store.ingest(_observation(metrics={"heart_rate": 99})))

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM outbox").fetchone() == (1,)
        assert connection.execute(
            "SELECT version FROM biometric_schema_versions WHERE name = 'canonical_observation_store'"
        ).fetchone() == (2,)
        assert "lease_until" in {row[1] for row in connection.execute("PRAGMA table_info(delivery_outbox)")}
        inbox = connection.execute("SELECT canonical_hash, canonical_json, status FROM observation_inbox").fetchone()
        assert len(inbox[0]) == 64
        assert json.loads(inbox[1])["source_ts"] == "2026-07-19T02:03:04Z"
        assert inbox[2] == "pending_delivery"
        rows = connection.execute(
            "SELECT destination, target, payload, status, attempts FROM delivery_outbox ORDER BY id"
        ).fetchall()
        assert len(rows) == 4  # heart_rate, spo2, steps, Backend canonical observation
        assert rows[-1][0:2] == ("backend", "/internal/biometric/observations")
        assert json.loads(rows[-1][2])["metrics"]["steps"] == 4321
        assert all(row[3:] == ("pending", 0) for row in rows)


def test_ingest_rolls_back_inbox_when_outbox_insert_fails(tmp_path):
    db_path = tmp_path / "rollback.db"
    store = CanonicalObservationStore(str(db_path))
    asyncio.run(store.init())
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """CREATE TRIGGER reject_delivery BEFORE INSERT ON delivery_outbox
               BEGIN SELECT RAISE(ABORT, 'forced delivery failure'); END"""
        )

    with pytest.raises(ObservationStoreError):
        asyncio.run(store.ingest(_observation()))

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM observation_inbox").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM delivery_outbox").fetchone() == (0,)


def test_private_ingest_auth_and_503_wiring(monkeypatch):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "internal-secret")
    with pytest.raises(HTTPException) as missing:
        verify_internal_token(None)
    assert missing.value.status_code == 401
    assert verify_internal_token("Bearer internal-secret") is None

    source = (_BRIDGE_SRC / "main.py").read_text()
    assert '@private_router.post("/api/biometric/ingest")' in source
    assert "except ObservationStoreError:" in source
    assert "status_code=503" in source
