"""Focused P1.2b canonical delivery worker tests."""

import asyncio
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_BRIDGE_SRC = _ROOT / "services" / "biometric-bridge" / "src"
sys.path.insert(0, str(_BRIDGE_SRC))

from canonical_delivery import CanonicalDeliveryWorker
from canonical_ingest import CanonicalObservationStore

from hems_common.biometric import BiometricObservationIn


class FakeBackendTransport:
    def __init__(self, statuses=()):
        self.statuses = list(statuses)
        self.calls = []
        self.started = False
        self.closed = False

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True

    async def post(self, url, payload, headers):
        self.calls.append((url, payload, headers))
        result = self.statuses.pop(0) if self.statuses else 200
        if isinstance(result, Exception):
            raise result
        return result


def _observation(observation_id="delivery:test:1", metrics=None):
    return BiometricObservationIn.model_validate(
        {
            "schema_version": 1,
            "observation_id": observation_id,
            "provider": "healthconnect",
            "source_ts": "2026-07-19T03:00:00Z",
            "aggregation": "sample",
            "metrics": metrics or {"heart_rate": 70},
        }
    )


def _store(tmp_path, name="delivery.db"):
    store = CanonicalObservationStore(str(tmp_path / name))
    asyncio.run(store.init())
    return store


def _rows(store):
    with sqlite3.connect(store.db_path) as connection:
        return connection.execute(
            "SELECT destination, target, status, attempts, last_error, next_attempt_at FROM delivery_outbox ORDER BY id"
        ).fetchall()


def _worker(store, mqtt_publish, transport, **overrides):
    params = {
        "store": store,
        "mqtt_publish": mqtt_publish,
        "backend_base_url": "http://backend:8000",
        "backend_transport": transport,
        "base_backoff_seconds": 10,
        "max_backoff_seconds": 60,
        "jitter_seconds": 5,
        "random_fn": lambda: 0.5,
    }
    params.update(overrides)
    return CanonicalDeliveryWorker(**params)


def test_mixed_batch_delivers_independently_without_legacy_double_queue(monkeypatch, tmp_path):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "worker-secret")
    store = _store(tmp_path)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            """CREATE TABLE outbox (
               id INTEGER PRIMARY KEY, topic TEXT, payload TEXT, retain INTEGER, created_at REAL, attempts INTEGER)"""
        )
    asyncio.run(store.ingest(_observation(metrics={"heart_rate": 70, "spo2": 98})))

    mqtt_calls = []

    def mqtt_publish(topic, payload):
        mqtt_calls.append((topic, payload))
        return not topic.endswith("/heart_rate")

    transport = FakeBackendTransport([200])
    worker = _worker(store, mqtt_publish, transport)
    assert asyncio.run(worker.process_batch()) == 3

    rows = _rows(store)
    assert [row[2] for row in rows] == ["retry", "sent", "sent"]
    assert len(mqtt_calls) == 2
    assert transport.calls[0][0] == "http://backend:8000/internal/biometric/observations"
    assert transport.calls[0][2] == {"Authorization": "Bearer worker-secret"}
    with sqlite3.connect(store.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM outbox").fetchone() == (0,)


@pytest.mark.parametrize(
    ("status", "expected", "error", "auth_fatal"),
    [
        (409, "dead_letter", "backend_observation_conflict", False),
        (401, "dead_letter", "backend_auth_failed", True),
        (403, "dead_letter", "backend_auth_failed", True),
        (422, "dead_letter", "backend_http_422", False),
        (500, "retry", "backend_http_500", False),
        (RuntimeError("offline"), "retry", "backend_network_error", False),
    ],
)
def test_backend_status_classification(tmp_path, status, expected, error, auth_fatal):
    store = _store(tmp_path, f"status-{status}.db")
    asyncio.run(store.ingest(_observation(f"delivery:status:{status}")))
    transport = FakeBackendTransport([status])
    worker = _worker(store, lambda _topic, _payload: True, transport)
    asyncio.run(worker.process_batch())

    backend = next(row for row in _rows(store) if row[0] == "backend")
    assert backend[2] == expected
    assert backend[4] == error
    assert worker.auth_fatal is auth_fatal


def test_retry_backoff_then_max_attempts_dead_letter(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.ingest(_observation()))
    worker = _worker(store, lambda _topic, _payload: False, FakeBackendTransport([200]), max_attempts=2)
    asyncio.run(worker.process_batch())

    mqtt = next(row for row in _rows(store) if row[0] == "mqtt")
    assert mqtt[2:5] == ("retry", 1, "mqtt_publish_failed")
    next_attempt = datetime.fromisoformat(mqtt[5])
    delay = (next_attempt - datetime.now(UTC)).total_seconds()
    assert 11 <= delay <= 13  # 10s base + deterministic 2.5s jitter

    with sqlite3.connect(store.db_path) as connection:
        connection.execute("UPDATE delivery_outbox SET next_attempt_at = NULL WHERE destination = 'mqtt'")
    asyncio.run(worker.process_batch())
    mqtt = next(row for row in _rows(store) if row[0] == "mqtt")
    assert mqtt[2] == "dead_letter"
    assert mqtt[3] == 2
    assert mqtt[4] == "max_attempts:mqtt_publish_failed"


def test_restart_recovers_stale_processing_lease(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.ingest(_observation()))
    claimed = asyncio.run(store.claim_due(batch_size=10, lease_seconds=60))
    assert len(claimed) == 2
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE delivery_outbox SET lease_until = ?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),),
        )

    restarted = CanonicalObservationStore(store.db_path)
    asyncio.run(restarted.init())
    worker = _worker(restarted, lambda _topic, _payload: True, FakeBackendTransport([200]))
    assert asyncio.run(worker.process_batch()) == 2
    assert {row[2] for row in _rows(restarted)} == {"sent"}


def test_worker_cancellation_closes_transport(tmp_path):
    store = _store(tmp_path)

    async def scenario():
        transport = FakeBackendTransport()
        worker = _worker(store, lambda _topic, _payload: True, transport, poll_seconds=3600)
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0)
        assert worker.running is True
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert worker.running is False
        assert transport.started is True
        assert transport.closed is True

    asyncio.run(scenario())
