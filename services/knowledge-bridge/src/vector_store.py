"""
In-memory vector store — cosine similarity search over numpy arrays.
"""
import numpy as np
from loguru import logger


class VectorStore:
    """In-memory vector index for embedding-based document search."""

    def __init__(self):
        self._keys: list[str] = []        # doc_key list (aligned with matrix rows)
        self._matrix: np.ndarray | None = None  # (N, dim) normalized vectors
        self._key_to_idx: dict[str, int] = {}

    @property
    def size(self) -> int:
        return len(self._keys)

    def add(self, doc_key: str, vector: np.ndarray):
        """Add or update a single document vector."""
        vec = self._normalize(vector)
        if doc_key in self._key_to_idx:
            idx = self._key_to_idx[doc_key]
            self._matrix[idx] = vec
        else:
            self._key_to_idx[doc_key] = len(self._keys)
            self._keys.append(doc_key)
            if self._matrix is None:
                self._matrix = vec.reshape(1, -1)
            else:
                self._matrix = np.vstack([self._matrix, vec.reshape(1, -1)])

    def remove(self, doc_key: str):
        """Remove a document from the store."""
        if doc_key not in self._key_to_idx:
            return
        idx = self._key_to_idx[doc_key]
        self._keys.pop(idx)
        if self._matrix is not None:
            self._matrix = np.delete(self._matrix, idx, axis=0)
            if self._matrix.shape[0] == 0:
                self._matrix = None
        # Rebuild index
        self._key_to_idx = {k: i for i, k in enumerate(self._keys)}

    def build_from_dict(self, vectors: dict[str, np.ndarray]):
        """Bulk-build the store from a {doc_key: vector} dict."""
        if not vectors:
            self._keys = []
            self._matrix = None
            self._key_to_idx = {}
            return

        self._keys = list(vectors.keys())
        self._key_to_idx = {k: i for i, k in enumerate(self._keys)}
        matrix = np.stack([self._normalize(vectors[k]) for k in self._keys])
        self._matrix = matrix
        logger.debug(f"VectorStore built: {len(self._keys)} vectors, dim={matrix.shape[1]}")

    def search(self, query_vector: np.ndarray, top_k: int = 20,
               allowed_keys: set[str] | None = None) -> list[tuple[str, float]]:
        """Cosine similarity search. Returns [(doc_key, score), ...] sorted desc.

        Args:
            query_vector: Query embedding.
            top_k: Max results.
            allowed_keys: If set, only search within these keys (for pre-filtering).
        """
        if self._matrix is None or len(self._keys) == 0:
            return []

        q = self._normalize(query_vector)

        if allowed_keys is not None:
            # Filter to allowed indices
            indices = [self._key_to_idx[k] for k in allowed_keys if k in self._key_to_idx]
            if not indices:
                return []
            sub_matrix = self._matrix[indices]
            scores = sub_matrix @ q
            top_idx = np.argsort(scores)[::-1][:top_k]
            return [(self._keys[indices[i]], float(scores[i])) for i in top_idx if scores[i] > 0]
        else:
            scores = self._matrix @ q
            top_idx = np.argsort(scores)[::-1][:top_k]
            return [(self._keys[i], float(scores[i])) for i in top_idx if scores[i] > 0]

    def _normalize(self, vec: np.ndarray) -> np.ndarray:
        """L2-normalize a vector for cosine similarity via dot product."""
        norm = np.linalg.norm(vec)
        if norm > 0:
            return vec / norm
        return vec
