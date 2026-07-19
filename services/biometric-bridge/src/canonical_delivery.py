"""Single-worker delivery for canonical biometric outbox intents."""

import asyncio
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import aiohttp
from canonical_ingest import CanonicalObservationStore, OutboxIntent

from hems_common.auth import internal_auth_headers


class AiohttpBackendTransport:
    def __init__(self, timeout_seconds: float = 10.0):
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(timeout=self._timeout)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def post(self, url: str, payload: dict, headers: dict[str, str]) -> int:
        if self._session is None:
            raise RuntimeError("backend transport is not started")
        async with self._session.post(url, json=payload, headers=headers) as response:
            return response.status


class CanonicalDeliveryWorker:
    """Claims delivery intents and relies on downstream observation IDs for idempotency."""

    def __init__(
        self,
        *,
        store: CanonicalObservationStore,
        mqtt_publish: Callable[[str, dict], bool],
        backend_base_url: str,
        backend_transport=None,
        batch_size: int = 50,
        poll_seconds: float = 2.0,
        lease_seconds: float = 60.0,
        max_attempts: int = 8,
        base_backoff_seconds: float = 2.0,
        max_backoff_seconds: float = 300.0,
        jitter_seconds: float = 1.0,
        random_fn: Callable[[], float] = random.random,
    ):
        self.store = store
        self.mqtt_publish = mqtt_publish
        self.backend_base_url = backend_base_url.rstrip("/")
        self.backend_transport = backend_transport or AiohttpBackendTransport()
        self.batch_size = batch_size
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.jitter_seconds = jitter_seconds
        self.random_fn = random_fn
        self.running = False
        self.auth_fatal = False
        self.last_success_at: str | None = None
        self.last_error: str | None = None

    async def run(self) -> None:
        await self.backend_transport.start()
        self.running = True
        try:
            while True:
                try:
                    await self.process_batch()
                except Exception:
                    self.last_error = "delivery_store_unavailable"
                await asyncio.sleep(self.poll_seconds)
        finally:
            self.running = False
            await self.backend_transport.close()

    async def process_batch(self) -> int:
        intents = await self.store.claim_due(batch_size=self.batch_size, lease_seconds=self.lease_seconds)
        for intent in intents:
            try:
                await self._deliver(intent)
            except Exception:
                await self._retry(intent, "worker_unexpected_error")
        return len(intents)

    async def _deliver(self, intent: OutboxIntent) -> None:
        if intent.destination == "mqtt":
            try:
                published = self.mqtt_publish(intent.target, intent.payload)
            except Exception:
                published = False
            if published:
                await self._sent(intent)
            else:
                await self._retry(intent, "mqtt_publish_failed")
            return

        if intent.destination != "backend":
            await self._dead_letter(intent, "unknown_destination")
            return

        try:
            status = await self.backend_transport.post(
                f"{self.backend_base_url}{intent.target}",
                intent.payload,
                internal_auth_headers(),
            )
        except Exception:
            await self._retry(intent, "backend_network_error")
            return

        if 200 <= status < 300:
            await self._sent(intent)
        elif status == 409:
            await self._dead_letter(intent, "backend_observation_conflict")
        elif status in (401, 403):
            self.auth_fatal = True
            await self._dead_letter(intent, "backend_auth_failed")
        elif 400 <= status < 500:
            await self._dead_letter(intent, f"backend_http_{status}")
        else:
            await self._retry(intent, f"backend_http_{status}")

    async def _sent(self, intent: OutboxIntent) -> None:
        await self.store.mark_sent(intent.id)
        self.last_success_at = datetime.now(UTC).isoformat()
        self.last_error = None

    async def _dead_letter(self, intent: OutboxIntent, error: str) -> None:
        await self.store.mark_failed(intent.id, error=error, next_attempt_at=None, permanent=True)
        self.last_error = error

    async def _retry(self, intent: OutboxIntent, error: str) -> None:
        next_attempt = intent.attempts + 1
        if next_attempt >= self.max_attempts:
            await self._dead_letter(intent, f"max_attempts:{error}")
            return
        delay = min(self.max_backoff_seconds, self.base_backoff_seconds * (2 ** max(0, intent.attempts)))
        jitter_room = max(0.0, self.max_backoff_seconds - delay)
        delay += self.random_fn() * min(self.jitter_seconds, jitter_room)
        await self.store.mark_failed(
            intent.id,
            error=error,
            next_attempt_at=datetime.now(UTC) + timedelta(seconds=delay),
            permanent=False,
        )
        self.last_error = error

    def status(self) -> dict:
        return {
            "running": self.running,
            "auth_fatal": self.auth_fatal,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
        }
