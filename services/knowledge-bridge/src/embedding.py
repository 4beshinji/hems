"""
Embedding client — generates document embeddings via Ollama API.
Gracefully degrades when Ollama is unavailable.
"""

import asyncio
import hashlib
import json
from pathlib import Path

import aiohttp
import numpy as np
from loguru import logger


class EmbeddingClient:
    """Async embedding client using Ollama /api/embed endpoint."""

    def __init__(self, url: str = "", model: str = "nomic-embed-text", cache_dir: str = ""):
        self.url = url.rstrip("/") if url else ""
        self.model = model
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._session: aiohttp.ClientSession | None = None
        self._dim: int = 0  # embedding dimension, detected on first call
        self._available: bool = False
        self._cache: dict[str, np.ndarray] = {}  # content_hash → vector

    @property
    def available(self) -> bool:
        return self._available

    @property
    def dim(self) -> int:
        return self._dim

    async def initialize(self):
        """Check Ollama connectivity and detect embedding dimension."""
        if not self.url:
            logger.info("Embedding disabled (EMBEDDING_URL not set)")
            return

        self._session = aiohttp.ClientSession()
        self._load_cache()

        # Probe with a short text to detect dimension and verify connectivity
        try:
            vec = await self._embed_single("test")
            if vec is not None:
                self._dim = len(vec)
                self._available = True
                logger.info(f"Embedding ready: model={self.model}, dim={self._dim}, cached={len(self._cache)}")
            else:
                logger.warning("Embedding probe failed — vector search disabled")
        except Exception as e:
            logger.warning(f"Embedding initialization failed: {e} — vector search disabled")

    async def close(self):
        self._save_cache()
        if self._session:
            await self._session.close()

    async def embed(self, text: str) -> np.ndarray | None:
        """Embed a single text. Returns None if unavailable."""
        if not self._available:
            return None

        # Check cache
        h = self._content_hash(text)
        if h in self._cache:
            return self._cache[h]

        vec = await self._embed_single(text)
        if vec is not None:
            self._cache[h] = vec
        return vec

    async def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[np.ndarray | None]:
        """Embed multiple texts in batches. Returns list aligned with input."""
        if not self._available:
            return [None] * len(texts)

        results: list[np.ndarray | None] = [None] * len(texts)
        uncached_indices = []
        uncached_texts = []

        for i, text in enumerate(texts):
            h = self._content_hash(text)
            if h in self._cache:
                results[i] = self._cache[h]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if not uncached_texts:
            return results

        logger.info(f"Embedding {len(uncached_texts)} documents ({len(texts) - len(uncached_texts)} cached)...")

        # Process in batches
        for start in range(0, len(uncached_texts), batch_size):
            batch = uncached_texts[start : start + batch_size]
            batch_indices = uncached_indices[start : start + batch_size]

            try:
                vectors = await self._embed_batch_request(batch)
                for idx, text, vec in zip(batch_indices, batch, vectors):
                    if vec is not None:
                        h = self._content_hash(text)
                        self._cache[h] = vec
                        results[idx] = vec
            except Exception as e:
                logger.warning(f"Batch embedding failed (batch {start}): {e}")

            # Brief yield to avoid blocking the event loop
            await asyncio.sleep(0)

        self._save_cache()
        cached_count = sum(1 for r in results if r is not None)
        logger.info(f"Embedding complete: {cached_count}/{len(texts)} vectors")
        return results

    async def _embed_single(self, text: str) -> np.ndarray | None:
        """Single text embedding via Ollama API."""
        try:
            async with self._session.post(
                f"{self.url}/api/embed",
                json={"model": self.model, "input": text},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                embeddings = data.get("embeddings", [])
                if embeddings:
                    return np.array(embeddings[0], dtype=np.float32)
                return None
        except Exception:
            return None

    async def _embed_batch_request(self, texts: list[str]) -> list[np.ndarray | None]:
        """Batch embedding via Ollama API (single request, multiple inputs)."""
        try:
            async with self._session.post(
                f"{self.url}/api/embed",
                json={"model": self.model, "input": texts},
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    return [None] * len(texts)
                data = await resp.json()
                embeddings = data.get("embeddings", [])
                results = []
                for i in range(len(texts)):
                    if i < len(embeddings):
                        results.append(np.array(embeddings[i], dtype=np.float32))
                    else:
                        results.append(None)
                return results
        except Exception as e:
            logger.debug(f"Batch embed request failed: {e}")
            return [None] * len(texts)

    def _content_hash(self, text: str) -> str:
        """Deterministic hash for cache key."""
        key = f"{self.model}:{text[:2000]}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def _load_cache(self):
        """Load cached embeddings from disk (JSON format)."""
        if not self._cache_dir:
            return
        # Migrate: remove legacy pickle cache to avoid arbitrary code execution
        legacy = self._cache_dir / "embeddings.pkl"
        if legacy.exists():
            try:
                legacy.unlink()
                logger.info("Removed legacy pickle embedding cache (migrated to JSON)")
            except Exception as e:
                logger.warning(f"Could not remove legacy pickle cache: {e}")

        cache_file = self._cache_dir / "embeddings_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, encoding="utf-8") as f:
                    raw = json.load(f)
                self._cache = {h: np.array(v, dtype=np.float32) for h, v in raw.items()}
                logger.debug(f"Loaded {len(self._cache)} cached embeddings")
            except Exception as e:
                logger.debug(f"Cache load failed: {e}")
                self._cache = {}

    def _save_cache(self):
        """Save cached embeddings to disk (JSON format)."""
        if not self._cache_dir or not self._cache:
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self._cache_dir / "embeddings_cache.json"
            raw = {h: v.tolist() for h, v in self._cache.items()}
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(raw, f)
            logger.debug(f"Saved {len(self._cache)} embeddings to cache")
        except Exception as e:
            logger.debug(f"Cache save failed: {e}")
