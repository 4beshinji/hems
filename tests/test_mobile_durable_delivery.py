"""Focused P1.3b route and delivery-worker tests with fake transports."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from mobile_delivery import MobileDeliveryWorker, MobileOutboxIntent
from mobile_observations import MobileObservationConflictError
from routers import mobile

_ROOT = Path(__file__).resolve().parent.parent


class _Request:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()
        self.headers = {"X-HEMS-Signature": "sha256=test"}

    async def body(self):
        return self._body


class _Transport:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []
        self.started = self.closed = False

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True

    async def post(self, url, payload, headers):
        self.calls.append((url, payload, headers))
        result = self.results.pop(0) if self.results else 200
        if isinstance(result, Exception):
            raise result
        return result


class _Store:
    def __init__(self, intents=()):
        self.intents = list(intents)
        self.sent = []
        self.failed = []

    async def claim_due(self, _batch, _lease):
        claimed, self.intents = self.intents, []
        return claimed

    async def mark_sent(self, intent_id):
        self.sent.append(intent_id)

    async def mark_failed(self, intent_id, error, next_attempt, permanent):
        self.failed.append((intent_id, error, next_attempt, permanent))


def _worker(store, transport, mqtt=lambda _topic, _payload: True, **overrides):
    params = dict(
        store=store,
        mqtt_publish=mqtt,
        biometric_bridge_url="http://biometric-bridge:8000",
        transport=transport,
        random_fn=lambda: 0,
    )
    params.update(overrides)
    return MobileDeliveryWorker(**params)


@pytest.mark.asyncio
async def test_route_accepts_legacy_and_v2_as_queued_not_published(monkeypatch):
    monkeypatch.setattr(mobile, "verify_signature_with_replay", lambda *_args: (True, "ok"))
    calls = []

    async def persist(_db, *, device, observations):
        calls.append((device.id, observations))
        return {"inserted": len(observations), "duplicates": 0}

    monkeypatch.setattr(mobile, "persist_mobile_observation_batch", persist)
    device = SimpleNamespace(id=4, hmac_secret="secret")
    legacy = await mobile.state_webhook(_Request({"ts": "2026-07-19T03:00:00Z", "battery_pct": 80}), object(), device)
    v2 = await mobile.state_webhook(
        _Request(
            {
                "schema_version": 2,
                "batch_id": "batch:1",
                "observations": [
                    {
                        "observation_id": "record:1",
                        "kind": "location",
                        "source_ts": "2026-07-19T03:00:00Z",
                        "data": {"lat": 35.0},
                    }
                ],
            }
        ),
        object(),
        device,
    )
    assert legacy.queued_observations == 1
    assert v2.queued_observations == 1
    assert legacy.published_topics == v2.published_topics == []
    assert len(calls) == 2
    assert "_publish_mobile_event" not in (_ROOT / "services/backend/routers/mobile.py").read_text()


@pytest.mark.asyncio
async def test_route_duplicate_conflict_and_database_failure(monkeypatch):
    monkeypatch.setattr(mobile, "verify_signature_with_replay", lambda *_args: (True, "ok"))
    device = SimpleNamespace(id=4, hmac_secret="secret")
    request = _Request({"ts": "2026-07-19T03:00:00Z", "battery_pct": 80})

    async def duplicate(*_args, **_kwargs):
        return {"inserted": 0, "duplicates": 1}

    monkeypatch.setattr(mobile, "persist_mobile_observation_batch", duplicate)
    response = await mobile.state_webhook(request, object(), device)
    assert response.idempotent is True
    assert response.duplicate_observations == 1

    async def conflict(*_args, **_kwargs):
        raise MobileObservationConflictError("record:1")

    monkeypatch.setattr(mobile, "persist_mobile_observation_batch", conflict)
    with pytest.raises(HTTPException) as conflict_error:
        await mobile.state_webhook(request, object(), device)
    assert conflict_error.value.status_code == 409

    async def unavailable(*_args, **_kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(mobile, "persist_mobile_observation_batch", unavailable)
    with pytest.raises(HTTPException) as db_error:
        await mobile.state_webhook(request, object(), device)
    assert db_error.value.status_code == 503


@pytest.mark.asyncio
async def test_worker_mixed_delivery_auth_and_no_extra_queue(monkeypatch):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "internal-secret")
    intents = [
        MobileOutboxIntent(1, "obs:1", "mqtt", "hems/personal/mobile/mobile.4/location", {"x": 1}, 0),
        MobileOutboxIntent(2, "obs:2", "biometric_bridge", "/api/biometric/ingest", {"x": 2}, 0),
    ]
    store, transport = _Store(intents), _Transport([200])
    mqtt_calls = []
    worker = _worker(store, transport, lambda topic, payload: not mqtt_calls.append((topic, payload)))
    assert await worker.process_batch() == 2
    assert store.sent == [1, 2]
    assert len(mqtt_calls) == 1
    assert transport.calls[0][0] == "http://biometric-bridge:8000/api/biometric/ingest"
    assert transport.calls[0][2] == {"Authorization": "Bearer internal-secret"}


@pytest.mark.parametrize(
    ("result", "permanent", "error"),
    [
        (409, True, "biometric_bridge_conflict"),
        (401, True, "biometric_bridge_http_401"),
        (429, False, "biometric_bridge_http_429"),
        (500, False, "biometric_bridge_http_500"),
        (RuntimeError("offline"), False, "biometric_bridge_network_error"),
    ],
)
def test_worker_http_classification(result, permanent, error):
    intent = MobileOutboxIntent(1, "obs:1", "biometric_bridge", "/api/biometric/ingest", {}, 0)
    store, transport = _Store([intent]), _Transport([result])
    asyncio.run(_worker(store, transport).process_batch())
    assert store.failed[0][1] == error
    assert store.failed[0][3] is permanent


def test_worker_max_attempts_and_lifecycle_cleanup():
    intent = MobileOutboxIntent(1, "obs:1", "mqtt", "topic", {}, 1)
    store, transport = _Store([intent]), _Transport()
    asyncio.run(_worker(store, transport, mqtt=lambda *_args: False, max_attempts=2).process_batch())
    assert store.failed[0][1] == "max_attempts:mqtt_publish_failed"
    assert store.failed[0][3] is True

    async def lifecycle():
        worker = _worker(_Store(), transport, poll_seconds=3600)
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert transport.started and transport.closed and not worker.running

    asyncio.run(lifecycle())
