"""
SQLite-backed send queue for MQTT messages.

Buffers messages when MQTT broker is unreachable, flushes on reconnect.
"""
import json
import time

import aiosqlite
from loguru import logger

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    payload TEXT NOT NULL,
    retain INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    attempts INTEGER DEFAULT 0
)
"""

_MAX_AGE_SECONDS = 24 * 60 * 60  # 24h TTL


class SendQueue:
    """Async SQLite queue for MQTT messages that failed to publish."""

    def __init__(self, db_path: str = "/app/data/send_queue.db"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(_SCHEMA)
        await self._db.commit()
        count = await self.pending_count()
        if count > 0:
            logger.info(f"Send queue initialized with {count} pending messages")

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def enqueue(self, topic: str, payload: dict, retain: bool = False):
        """Add a message to the outbox."""
        if not self._db:
            return
        await self._db.execute(
            "INSERT INTO outbox (topic, payload, retain, created_at) VALUES (?, ?, ?, ?)",
            (topic, json.dumps(payload, ensure_ascii=False), int(retain), time.time()),
        )
        await self._db.commit()

    async def flush(self, publisher) -> int:
        """Publish pending messages via the given MQTTPublisher.

        Returns the number of successfully flushed messages.
        """
        if not self._db or not publisher or not publisher.connected:
            return 0

        # Prune expired messages first
        cutoff = time.time() - _MAX_AGE_SECONDS
        await self._db.execute("DELETE FROM outbox WHERE created_at < ?", (cutoff,))
        await self._db.commit()

        cursor = await self._db.execute(
            "SELECT id, topic, payload, retain FROM outbox ORDER BY created_at ASC LIMIT 100"
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0

        flushed = 0
        for row_id, topic, payload_str, retain in rows:
            try:
                data = json.loads(payload_str)
            except json.JSONDecodeError:
                await self._db.execute("DELETE FROM outbox WHERE id = ?", (row_id,))
                continue

            if publisher.publish(topic, data, retain=bool(retain)):
                await self._db.execute("DELETE FROM outbox WHERE id = ?", (row_id,))
                flushed += 1
            else:
                # MQTT went down mid-flush — stop and retry later
                break

        if flushed > 0:
            await self._db.commit()
            logger.info(f"Send queue flushed {flushed} messages")
        return flushed

    async def pending_count(self) -> int:
        if not self._db:
            return 0
        cursor = await self._db.execute("SELECT COUNT(*) FROM outbox")
        row = await cursor.fetchone()
        return row[0] if row else 0
