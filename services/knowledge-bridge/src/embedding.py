"""
Embedding client — generates document embeddings via an OpenAI-compatible
`/v1/embeddings` endpoint. Defaults to text-embeddings-inference (TEI) but
works with any OpenAI-compatible server (llama.cpp embeddings mode, LocalAI,
Ollama's `/v1` shim, etc.). Gracefully degrades when the server is unreachable.
"""
import asyncio
import hashlib
import json
import pickle
from pathlib import Path
from typing import Optional

import aiohttp
import numpy as np
from loguru import logger

from config import EMBEDDING_URL, EMBEDDING_MODEL, EMBEDDING_CACHE_DIR


class EmbeddingClient:
    """Async embedding client using OpenAI-compatible `/v1/embeddings`."""

    def __init__(self, url: str = "", model: str = "nomic-embed-text-v1.5",
                 cache_dir: str = ""):
        base = url.rstrip("/") if url else ""
        if base.endswith("/v1"):
            base = base[:-3]
        self.url = base
        self.model = model
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._session: Optional[aiohttp.ClientSession] = None
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
        """Probe the embedding server and detect embedding dimension."""
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
                logger.info(f"Embedding ready: model={self.model}, dim={self._dim}, "
                            f"cached={len(self._cache)}")
            else:
                logger.warning(f"Embedding probe failed — vector search disabled")
        except Exception as e:
            logger.warning(f"Embedding initialization failed: {e} — vector search disabled")

    async def close(self):
        self._save_cache()
        if self._session:
            await self._session.close()

    async def embed(self, text: str) -> Optional[np.ndarray]:
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

    async def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[Optional[np.ndarray]]:
        """Embed multiple texts in batches. Returns list aligned with input."""
        if not self._available:
            return [None] * len(texts)

        results: list[Optional[np.ndarray]] = [None] * len(texts)
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

        logger.info(f"Embedding {len(uncached_texts)} documents "
                    f"({len(texts) - len(uncached_texts)} cached)...")

        # Process in batches
        for start in range(0, len(uncached_texts), batch_size):
            batch = uncached_texts[start:start + batch_size]
            batch_indices = uncached_indices[start:start + batch_size]

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

    def _parse_vectors(self, data: dict, expected: int) -> list[Optional[np.ndarray]]:
        """Pull vectors out of an OpenAI or Ollama embedding response.

        OpenAI shape:  {"data": [{"embedding": [...], "index": 0}, ...]}
        Ollama shape:  {"embeddings": [[...], [...]]}  (fallback for legacy)
        """
        results: list[Optional[np.ndarray]] = [None] * expected
        items = data.get("data")
        if isinstance(items, list) and items:
            for item in items:
                idx = item.get("index", 0)
                vec = item.get("embedding")
                if vec is None or idx >= expected:
                    continue
                results[idx] = np.array(vec, dtype=np.float32)
            return results
        legacy = data.get("embeddings")
        if isinstance(legacy, list):
            for i, vec in enumerate(legacy[:expected]):
                results[i] = np.array(vec, dtype=np.float32)
        return results

    async def _embed_single(self, text: str) -> Optional[np.ndarray]:
        """Single text embedding via OpenAI-compatible `/v1/embeddings`."""
        try:
            async with self._session.post(
                f"{self.url}/v1/embeddings",
                json={"model": self.model, "input": text},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                vectors = self._parse_vectors(data, 1)
                return vectors[0]
        except Exception:
            return None

    async def _embed_batch_request(self, texts: list[str]) -> list[Optional[np.ndarray]]:
        """Batch embedding via OpenAI-compatible `/v1/embeddings`."""
        try:
            async with self._session.post(
                f"{self.url}/v1/embeddings",
                json={"model": self.model, "input": texts},
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    return [None] * len(texts)
                data = await resp.json()
                return self._parse_vectors(data, len(texts))
        except Exception as e:
            logger.debug(f"Batch embed request failed: {e}")
            return [None] * len(texts)

    def _content_hash(self, text: str) -> str:
        """Deterministic hash for cache key."""
        key = f"{self.model}:{text[:2000]}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def _load_cache(self):
        """Load cached embeddings from disk."""
        if not self._cache_dir:
            return
        cache_file = self._cache_dir / "embeddings.pkl"
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    self._cache = pickle.load(f)
                logger.debug(f"Loaded {len(self._cache)} cached embeddings")
            except Exception as e:
                logger.debug(f"Cache load failed: {e}")
                self._cache = {}

    def _save_cache(self):
        """Save cached embeddings to disk."""
        if not self._cache_dir or not self._cache:
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self._cache_dir / "embeddings.pkl"
            with open(cache_file, "wb") as f:
                pickle.dump(self._cache, f)
            logger.debug(f"Saved {len(self._cache)} embeddings to cache")
        except Exception as e:
            logger.debug(f"Cache save failed: {e}")
