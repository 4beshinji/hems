"""Durable mobile observation delivery worker."""

import asyncio
import os
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiohttp
from sqlalchemy import func, select, update

import models
from database import AsyncSessionLocal
from hems_common.auth import internal_auth_headers


@dataclass(frozen=True)
class MobileOutboxIntent:
    id: int
    observation_id: str
    destination: str
    target: str
    payload: dict
    attempts: int


class MobileDeliveryStore:
    def __init__(self, session_factory=AsyncSessionLocal):
        self.session_factory = session_factory

    async def claim_due(self, batch_size: int, lease_seconds: float) -> list[MobileOutboxIntent]:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            await session.execute(
                update(models.MobileDeliveryOutbox)
                .where(
                    models.MobileDeliveryOutbox.status == "processing",
                    models.MobileDeliveryOutbox.lease_until <= now,
                )
                .values(status="retry", lease_until=None, updated_at=now)
            )
            result = await session.execute(
                select(models.MobileDeliveryOutbox)
                .where(
                    models.MobileDeliveryOutbox.status.in_(("pending", "retry")),
                    (models.MobileDeliveryOutbox.next_attempt_at.is_(None))
                    | (models.MobileDeliveryOutbox.next_attempt_at <= now),
                )
                .order_by(models.MobileDeliveryOutbox.created_at, models.MobileDeliveryOutbox.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            rows = result.scalars().all()
            lease_until = now + timedelta(seconds=lease_seconds)
            for row in rows:
                row.status = "processing"
                row.lease_until = lease_until
                row.updated_at = now
            await session.commit()
        return [
            MobileOutboxIntent(row.id, row.observation_id, row.destination, row.target, row.payload, row.attempts)
            for row in rows
        ]

    async def mark_sent(self, intent_id: int) -> None:
        await self._mark(intent_id, status="sent", error=None, next_attempt=None, increment=False)

    async def mark_failed(self, intent_id: int, error: str, next_attempt: datetime | None, permanent: bool) -> None:
        await self._mark(
            intent_id,
            status="dead_letter" if permanent else "retry",
            error=error[:256],
            next_attempt=next_attempt,
            increment=True,
        )

    async def _mark(self, intent_id, *, status, error, next_attempt, increment):
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            row = await session.get(models.MobileDeliveryOutbox, intent_id, with_for_update=True)
            if row is None or row.status != "processing":
                return
            row.status = status
            row.attempts += int(increment)
            row.last_error = error
            row.next_attempt_at = next_attempt
            row.lease_until = None
            row.updated_at = now
            await session.flush()
            active = await session.scalar(
                select(func.count()).where(
                    models.MobileDeliveryOutbox.observation_id == row.observation_id,
                    models.MobileDeliveryOutbox.status.in_(("pending", "retry", "processing")),
                )
            )
            failed = await session.scalar(
                select(func.count()).where(
                    models.MobileDeliveryOutbox.observation_id == row.observation_id,
                    models.MobileDeliveryOutbox.status == "dead_letter",
                )
            )
            inbox = await session.get(models.MobileObservationInbox, row.observation_id, with_for_update=True)
            if inbox:
                inbox.status = "pending_delivery" if active else "delivery_failed" if failed else "delivered"
            await session.commit()

    async def counts(self) -> dict[str, int]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.MobileDeliveryOutbox.status, func.count()).group_by(models.MobileDeliveryOutbox.status)
            )
            return dict(result.all())


class BackendHttpTransport:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None

    async def start(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def post(self, url, payload, headers) -> int:
        if self.session is None:
            raise RuntimeError("transport not started")
        async with self.session.post(url, json=payload, headers=headers) as response:
            return response.status


class MobileDeliveryWorker:
    def __init__(
        self,
        *,
        store,
        mqtt_publish: Callable[[str, dict], bool],
        biometric_bridge_url: str,
        transport=None,
        batch_size=50,
        poll_seconds=2.0,
        lease_seconds=60.0,
        max_attempts=8,
        base_backoff=2.0,
        max_backoff=300.0,
        jitter=1.0,
        random_fn=random.random,
    ):
        self.store = store
        self.mqtt_publish = mqtt_publish
        self.biometric_bridge_url = biometric_bridge_url.rstrip("/")
        self.transport = transport or BackendHttpTransport()
        self.batch_size = batch_size
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self.jitter = jitter
        self.random_fn = random_fn
        self.running = False
        self.last_error = None
        self.last_success_at = None

    async def run(self):
        await self.transport.start()
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
            await self.transport.close()

    async def process_batch(self):
        intents = await self.store.claim_due(self.batch_size, self.lease_seconds)
        for intent in intents:
            try:
                await self._deliver(intent)
            except Exception:
                await self._retry(intent, "worker_unexpected_error")
        return len(intents)

    async def _deliver(self, intent):
        if intent.destination == "mqtt":
            if self.mqtt_publish(intent.target, intent.payload):
                await self._sent(intent)
            else:
                await self._retry(intent, "mqtt_publish_failed")
            return
        if intent.destination != "biometric_bridge":
            await self._dead(intent, "unknown_destination")
            return
        try:
            status = await self.transport.post(
                f"{self.biometric_bridge_url}{intent.target}", intent.payload, internal_auth_headers()
            )
        except Exception:
            await self._retry(intent, "biometric_bridge_network_error")
            return
        if 200 <= status < 300:
            await self._sent(intent)
        elif status == 429 or status >= 500:
            await self._retry(intent, f"biometric_bridge_http_{status}")
        elif 400 <= status < 500:
            await self._dead(
                intent, "biometric_bridge_conflict" if status == 409 else f"biometric_bridge_http_{status}"
            )
        else:
            await self._retry(intent, f"biometric_bridge_http_{status}")

    async def _sent(self, intent):
        await self.store.mark_sent(intent.id)
        self.last_success_at = datetime.now(UTC).isoformat()
        self.last_error = None

    async def _dead(self, intent, error):
        await self.store.mark_failed(intent.id, error, None, True)
        self.last_error = error

    async def _retry(self, intent, error):
        if intent.attempts + 1 >= self.max_attempts:
            await self._dead(intent, f"max_attempts:{error}")
            return
        delay = min(self.max_backoff, self.base_backoff * (2**intent.attempts))
        delay += self.random_fn() * min(self.jitter, max(0, self.max_backoff - delay))
        await self.store.mark_failed(intent.id, error, datetime.now(UTC) + timedelta(seconds=delay), False)
        self.last_error = error

    def status(self):
        return {"running": self.running, "last_error": self.last_error, "last_success_at": self.last_success_at}


def worker_config() -> dict:
    return {
        "batch_size": int(os.getenv("MOBILE_DELIVERY_BATCH_SIZE", "50")),
        "poll_seconds": float(os.getenv("MOBILE_DELIVERY_POLL_SECONDS", "2")),
        "lease_seconds": float(os.getenv("MOBILE_DELIVERY_LEASE_SECONDS", "60")),
        "max_attempts": int(os.getenv("MOBILE_DELIVERY_MAX_ATTEMPTS", "8")),
        "base_backoff": float(os.getenv("MOBILE_DELIVERY_BASE_BACKOFF_SECONDS", "2")),
        "max_backoff": float(os.getenv("MOBILE_DELIVERY_MAX_BACKOFF_SECONDS", "300")),
    }
