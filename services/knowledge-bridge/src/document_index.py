"""
Document indexer — multi-source, multi-format hybrid search index.
3-way Reciprocal Rank Fusion: BM25 + Vector (embedding) + Title boost.
Graceful degradation: vector search disabled when the embedding server is unavailable.
"""

import re
import time
from pathlib import Path

import numpy as np
from embedding import EmbeddingClient
from loaders import DocumentEntry, get_loader
from loguru import logger
from rank_bm25 import BM25Okapi
from vector_store import VectorStore

from config import DEFAULT_EXCLUDE_PATTERNS, DEFAULT_EXTENSIONS, RRF_K

# Recent boost: documents modified in last 24h get 1.2x score
RECENT_WINDOW = 86400
RECENT_BOOST = 1.2

# Truncate body text for embedding (token budget)
EMBED_MAX_CHARS = 4000

# Stop words (Japanese + English)
_STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "have",
        "has",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "this",
        "that",
        "it",
        "not",
        "no",
        "from",
        "as",
        "if",
        "so",
        "の",
        "は",
        "が",
        "を",
        "に",
        "で",
        "と",
        "も",
        "や",
        "から",
        "まで",
        "する",
        "いる",
        "ある",
        "なる",
        "れる",
        "られる",
        "こと",
        "もの",
        "ため",
        "self",
        "def",
        "class",
        "import",
        "return",
        "none",
        "true",
        "false",
    }
)


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: split on whitespace/punctuation, lowercase."""
    text = re.sub(r"[#*_`~\[\](){}|>]", " ", text)
    text = re.sub(r"https?://\S+", "", text)
    tokens = re.findall(r"[\w\u3040-\u9fff\u30a0-\u30ff\uff00-\uffef]+", text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


def _rrf_fuse(ranked_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion over multiple ranked doc_key lists.

    score(d) = Σ  1 / (k + rank_i(d))
    where rank_i is 1-based rank in list i.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank_0, doc_key in enumerate(ranked):
            scores[doc_key] = scores.get(doc_key, 0.0) + 1.0 / (k + rank_0 + 1)
    return scores


class DocumentIndex:
    """Multi-source, multi-format hybrid search index.

    Search pipeline:
      1. BM25 keyword scoring over tokenized body text
      2. Vector cosine similarity via OpenAI-compat embeddings (optional)
      3. Title BM25 scoring (separate index, title-only corpus)
      4. 3-way RRF fusion → final ranked results
    """

    def __init__(self, embedding_client: EmbeddingClient | None = None):
        self.documents: dict[str, DocumentEntry] = {}  # "{source}:{path}" → entry
        self._sources: dict[str, dict] = {}
        self._doc_keys: list[str] = []  # ordered list, aligned with BM25 corpus

        # BM25 (body)
        self._bm25: BM25Okapi | None = None
        self._tokenized_corpus: list[list[str]] = []

        # BM25 (title)
        self._title_bm25: BM25Okapi | None = None
        self._title_corpus: list[list[str]] = []

        # Vector search
        self._embedder = embedding_client
        self._vectors = VectorStore()

    # ------------------------------------------------------------------
    # Source management
    # ------------------------------------------------------------------

    def add_source(
        self, name: str, path: str, extensions: list[str] | None = None, exclude_patterns: list[str] | None = None
    ):
        """Register a source directory for indexing."""
        source_path = Path(path)
        if not source_path.exists():
            logger.warning(f"Source '{name}' path does not exist: {path}")
            self._sources[name] = {
                "path": path,
                "extensions": extensions or DEFAULT_EXTENSIONS,
                "exclude_patterns": exclude_patterns or DEFAULT_EXCLUDE_PATTERNS,
                "active": False,
            }
            return

        self._sources[name] = {
            "path": path,
            "extensions": extensions or DEFAULT_EXTENSIONS,
            "exclude_patterns": exclude_patterns or DEFAULT_EXCLUDE_PATTERNS,
            "active": True,
        }
        logger.info(f"Source '{name}' registered: {path}")

    def build_source_index(self, source_name: str):
        """Index all documents in a source directory."""
        src = self._sources.get(source_name)
        if not src or not src["active"]:
            logger.warning(f"Source '{source_name}' not active, skipping")
            return

        start = time.time()
        source_path = Path(src["path"])
        extensions = set(src["extensions"])
        exclude = src["exclude_patterns"]
        count = 0

        # Remove existing entries for this source
        keys_to_remove = [k for k in self.documents if k.startswith(f"{source_name}:")]
        for k in keys_to_remove:
            del self.documents[k]

        for file_path in source_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in extensions:
                continue

            rel = str(file_path.relative_to(source_path))
            if self._should_exclude(rel, exclude):
                continue

            try:
                self._load_file(source_name, source_path, rel)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to index {source_name}:{rel}: {e}")

        elapsed = time.time() - start
        logger.info(f"Source '{source_name}': loaded {count} documents in {elapsed:.2f}s")

    def build_all(self):
        """Load all registered sources, then rebuild search indices."""
        for name in self._sources:
            self.build_source_index(name)
        self._rebuild_bm25()

    async def build_vectors(self):
        """Build vector index from loaded documents (async, needs embedding server)."""
        if not self._embedder or not self._embedder.available:
            logger.info("Vector index skipped (embedding not available)")
            return

        texts = []
        keys = []
        for doc_key, entry in self.documents.items():
            texts.append(entry.body[:EMBED_MAX_CHARS])
            keys.append(doc_key)

        vectors = await self._embedder.embed_batch(texts)

        vec_dict: dict[str, np.ndarray] = {}
        for key, vec in zip(keys, vectors):
            if vec is not None:
                vec_dict[key] = vec

        self._vectors.build_from_dict(vec_dict)
        logger.info(f"Vector index built: {self._vectors.size}/{len(keys)} documents embedded")

    def reindex_file(self, source_name: str, rel_path: str):
        """Re-index a single file (for incremental updates)."""
        src = self._sources.get(source_name)
        if not src or not src["active"]:
            return

        source_path = Path(src["path"])
        full = source_path / rel_path
        doc_key = f"{source_name}:{rel_path}"

        if not full.exists():
            if doc_key in self.documents:
                del self.documents[doc_key]
                self._vectors.remove(doc_key)
                self._rebuild_bm25()
            return

        if self._should_exclude(rel_path, src["exclude_patterns"]):
            return

        self._load_file(source_name, source_path, rel_path)
        self._rebuild_bm25()

    async def reindex_file_with_vector(self, source_name: str, rel_path: str):
        """Re-index a single file including vector embedding."""
        self.reindex_file(source_name, rel_path)
        doc_key = f"{source_name}:{rel_path}"
        entry = self.documents.get(doc_key)
        if entry and self._embedder and self._embedder.available:
            vec = await self._embedder.embed(entry.body[:EMBED_MAX_CHARS])
            if vec is not None:
                self._vectors.add(doc_key, vec)

    def remove_file(self, source_name: str, rel_path: str):
        """Remove a file from the index."""
        doc_key = f"{source_name}:{rel_path}"
        if doc_key in self.documents:
            del self.documents[doc_key]
            self._vectors.remove(doc_key)
            self._rebuild_bm25()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        source: str | None = None,
        doc_type: str | None = None,
        tags: list[str] | None = None,
        path_prefix: str | None = None,
        max_results: int = 10,
    ) -> list[dict]:
        """Hybrid search: BM25 + Vector + Title boost via 3-way RRF."""
        query_tokens = _tokenize(query)
        has_query = bool(query.strip())
        filter_only = not has_query and (tags or path_prefix or source or doc_type)

        if not has_query and not filter_only:
            return []

        # Pre-filter candidates
        candidates = self._filter_candidates(source, doc_type, tags, path_prefix)
        if not candidates:
            return []

        if not has_query:
            # Filter-only: return by recency
            now = time.time()
            items = [
                (k, 1.0 + (RECENT_BOOST - 1.0 if now - self.documents[k].modified_at < RECENT_WINDOW else 0))
                for k in candidates
            ]
            items.sort(key=lambda x: self.documents[x[0]].modified_at, reverse=True)
            return self._build_results(items[:max_results])

        candidate_set = set(candidates)
        ranked_lists: list[list[str]] = []

        # --- Signal 1: BM25 (body) ---
        if query_tokens and self._bm25 is not None:
            bm25_scores = self._bm25.get_scores(query_tokens)
            bm25_ranked = [
                self._doc_keys[i]
                for i in sorted(range(len(self._doc_keys)), key=lambda i: bm25_scores[i], reverse=True)
                if self._doc_keys[i] in candidate_set and bm25_scores[i] > 0
            ]
            if bm25_ranked:
                ranked_lists.append(bm25_ranked)

        # --- Signal 2: Vector (semantic) ---
        if has_query and self._embedder and self._embedder.available and self._vectors.size > 0:
            query_vec = await self._embedder.embed(query)
            if query_vec is not None:
                vec_results = self._vectors.search(
                    query_vec,
                    top_k=max_results * 3,
                    allowed_keys=candidate_set,
                )
                vec_ranked = [doc_key for doc_key, _score in vec_results]
                if vec_ranked:
                    ranked_lists.append(vec_ranked)

        # --- Signal 3: Title BM25 ---
        if query_tokens and self._title_bm25 is not None:
            title_scores = self._title_bm25.get_scores(query_tokens)
            title_ranked = [
                self._doc_keys[i]
                for i in sorted(range(len(self._doc_keys)), key=lambda i: title_scores[i], reverse=True)
                if self._doc_keys[i] in candidate_set and title_scores[i] > 0
            ]
            if title_ranked:
                ranked_lists.append(title_ranked)

        if not ranked_lists:
            return []

        # --- RRF fusion ---
        rrf_scores = _rrf_fuse(ranked_lists, k=RRF_K)

        # Recent boost (multiplicative)
        now = time.time()
        for doc_key in rrf_scores:
            entry = self.documents[doc_key]
            if now - entry.modified_at < RECENT_WINDOW:
                rrf_scores[doc_key] *= RECENT_BOOST

        # Sort and return
        sorted_keys = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:max_results]
        return self._build_results([(k, rrf_scores[k]) for k in sorted_keys])

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_recent(self, limit: int = 10, source: str | None = None) -> list[dict]:
        entries = self.documents.values()
        if source:
            entries = [e for e in entries if e.source_name == source]
        sorted_docs = sorted(entries, key=lambda d: d.modified_at, reverse=True)
        return [
            {
                "source": d.source_name,
                "path": d.path,
                "title": d.title,
                "doc_type": d.doc_type,
                "tags": d.tags,
                "modified_at": d.modified_at,
                "word_count": d.word_count,
            }
            for d in sorted_docs[:limit]
        ]

    def get_source_stats(self) -> list[dict]:
        stats = []
        for name, src in self._sources.items():
            doc_count = sum(1 for d in self.documents.values() if d.source_name == name)
            type_counts: dict[str, int] = {}
            for d in self.documents.values():
                if d.source_name == name:
                    type_counts[d.doc_type] = type_counts.get(d.doc_type, 0) + 1
            stats.append(
                {
                    "name": name,
                    "path": src["path"],
                    "active": src["active"],
                    "doc_count": doc_count,
                    "type_counts": type_counts,
                    "extensions": src["extensions"],
                    "vector_indexed": self._vectors.size if self._embedder and self._embedder.available else 0,
                }
            )
        return stats

    def get_total_docs(self) -> int:
        return len(self.documents)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _should_exclude(self, rel_path: str, exclude_patterns: list[str]) -> bool:
        parts = Path(rel_path).parts
        for pattern in exclude_patterns:
            if pattern.startswith("."):
                if any(part.startswith(".") for part in parts):
                    return True
            elif any(part == pattern for part in parts):
                return True
        return False

    def _load_file(self, source_name: str, source_path: Path, rel_path: str):
        """Load a file into self.documents via the appropriate loader."""
        full = source_path / rel_path
        loader = get_loader(full)
        entry = loader.load(full, rel_path, source_name)
        if entry:
            self.documents[f"{source_name}:{rel_path}"] = entry

    def _rebuild_bm25(self):
        """Rebuild BM25 indices (body + title) from current documents."""
        self._doc_keys = list(self.documents.keys())

        if not self._doc_keys:
            self._bm25 = None
            self._title_bm25 = None
            return

        self._tokenized_corpus = [_tokenize(self.documents[k].body) for k in self._doc_keys]
        self._title_corpus = [_tokenize(self.documents[k].title) for k in self._doc_keys]

        self._bm25 = BM25Okapi(self._tokenized_corpus)
        self._title_bm25 = BM25Okapi(self._title_corpus)

        logger.debug(f"BM25 indices rebuilt: {len(self._doc_keys)} documents")

    def _filter_candidates(
        self, source: str | None, doc_type: str | None, tags: list[str] | None, path_prefix: str | None
    ) -> list[str]:
        """Pre-filter doc_keys by source/type/tags/path."""
        result = []
        for doc_key, entry in self.documents.items():
            if source and entry.source_name != source:
                continue
            if doc_type and entry.doc_type != doc_type:
                continue
            if path_prefix and not entry.path.startswith(path_prefix):
                continue
            if tags and not any(t in entry.tags for t in tags):
                continue
            result.append(doc_key)
        return result

    def _build_results(self, scored_keys: list[tuple[str, float]]) -> list[dict]:
        """Convert (doc_key, score) list to API response dicts."""
        results = []
        for doc_key, score in scored_keys:
            entry = self.documents[doc_key]
            snippet = entry.body.strip()[:200]
            results.append(
                {
                    "source": entry.source_name,
                    "path": entry.path,
                    "title": entry.title,
                    "doc_type": entry.doc_type,
                    "tags": entry.tags,
                    "score": round(score, 4),
                    "snippet": snippet,
                    "modified_at": entry.modified_at,
                    "word_count": entry.word_count,
                }
            )
        return results
