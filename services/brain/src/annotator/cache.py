"""ClassifierCache — in-memory L1 + optional backend HTTP persistence.

Keyed by sha256(kind + ":" + normalized_input). The backend stores a
canonical JSON payload in ``value_json``; here we treat it as an opaque
string and let callers do their own encode/decode.

If ``session`` / ``backend_url`` aren't provided the cache works purely
in-memory — useful for unit tests and for P1-style seed-only flows that
don't need cross-restart persistence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from brain_constants import backend_auth_headers

if TYPE_CHECKING:
    import aiohttp


def _normalize(text: str) -> str:
    return text.strip().lower()


def hash_key(kind: str, key: str) -> str:
    return hashlib.sha256(f"{kind}:{_normalize(key)}".encode()).hexdigest()


@dataclass
class CacheEntry:
    value: str  # opaque — JSON-encoded by the caller if needed
    source: str  # seed | llm | user_override | promoted
    hit_count: int = 1


class ClassifierCache:
    def __init__(
        self,
        *,
        session: aiohttp.ClientSession | None = None,
        backend_url: str = "",
    ) -> None:
        self.session = session
        self.backend_url = backend_url.rstrip("/")
        self._memory: dict[str, CacheEntry] = {}

    # --- synchronous seed-path (no network) ------------------------------- #

    def get_memory(self, kind: str, key: str) -> CacheEntry | None:
        entry = self._memory.get(hash_key(kind, key))
        if entry is not None:
            entry.hit_count += 1
        return entry

    def put_memory(self, kind: str, key: str, value: str, source: str) -> None:
        self._memory[hash_key(kind, key)] = CacheEntry(value=value, source=source)

    # --- async HTTP-backed ------------------------------------------------ #

    async def get(self, kind: str, key: str) -> CacheEntry | None:
        """L1 in-memory → backend. On hit, cache in L1 for the rest of the process."""
        mem = self.get_memory(kind, key)
        if mem is not None:
            return mem
        if self.session is None or not self.backend_url:
            return None

        h = hash_key(kind, key)
        url = f"{self.backend_url}/classifier-cache/{kind}/{h}"
        try:
            async with self.session.get(url, headers=backend_auth_headers(), timeout=10) as resp:
                if resp.status == 404:
                    return None
                if resp.status != 200:
                    logger.debug("classifier-cache GET miss status={}", resp.status)
                    return None
                data = await resp.json()
                entry = CacheEntry(
                    value=data.get("value_json", ""),
                    source=data.get("source", "llm"),
                    hit_count=int(data.get("hit_count", 1)),
                )
                self._memory[h] = entry
                return entry
        except Exception as exc:
            logger.debug("classifier-cache GET error: {}", exc)
            return None

    async def put(self, kind: str, key: str, value: str, source: str) -> bool:
        """Upsert the entry to backend (if reachable) and L1. Returns success."""
        self.put_memory(kind, key, value, source)
        if self.session is None or not self.backend_url:
            return True  # memory-only mode, always success

        url = f"{self.backend_url}/classifier-cache"
        payload = {
            "kind": kind,
            "key_hash": hash_key(kind, key),
            "value_json": value,
            "source": source,
        }
        try:
            async with self.session.post(
                url,
                headers=backend_auth_headers(),
                json=payload,
                timeout=10,
            ) as resp:
                if resp.status == 201:
                    return True
                text = await resp.text()
                logger.warning(
                    "classifier-cache PUT failed status={} body={}",
                    resp.status,
                    text[:200],
                )
        except Exception as exc:
            logger.warning("classifier-cache PUT error: {}", exc)
        return False

    # --- small JSON helpers (callers produce/consume opaque strings) ------ #

    @staticmethod
    def encode(value) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def decode(raw: str):
        try:
            return json.loads(raw)
        except Exception:
            return raw
