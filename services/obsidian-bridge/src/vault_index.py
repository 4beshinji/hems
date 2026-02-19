"""
Vault indexer — scans Obsidian vault, builds TF-IDF keyword search index.
"""
import os
import re
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger

# Frontmatter parsing
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_TAG_INLINE_RE = re.compile(r"(?:^|\s)#([a-zA-Z0-9_/\u3040-\u9fff-]+)", re.UNICODE)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

# Recent boost: notes modified in last 24h get 1.5x score
RECENT_WINDOW = 86400
RECENT_BOOST = 1.5

# Stop words (minimal, Japanese + English common)
_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "have", "has",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by",
    "this", "that", "it", "not", "no", "from", "as", "if", "so",
    "の", "は", "が", "を", "に", "で", "と", "も", "や", "から", "まで",
    "する", "いる", "ある", "なる", "れる", "られる", "こと", "もの", "ため",
})


@dataclass
class NoteEntry:
    path: str  # relative to vault root
    title: str
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    word_count: int = 0
    modified_at: float = 0
    content: str = ""


class VaultIndex:
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.notes: dict[str, NoteEntry] = {}  # keyed by relative path
        # TF-IDF structures
        self._tf: dict[str, dict[str, float]] = {}  # doc_path → {term: tf}
        self._df: dict[str, int] = {}  # term → doc_frequency
        self._doc_count: int = 0

    def build_full_index(self):
        """Scan entire vault and build index."""
        start = time.time()
        count = 0
        for md_file in self.vault_path.rglob("*.md"):
            rel = str(md_file.relative_to(self.vault_path))
            # Skip hidden directories (.obsidian, .trash)
            if any(part.startswith(".") for part in Path(rel).parts):
                continue
            try:
                self._index_file(rel)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to index {rel}: {e}")

        self._rebuild_idf()
        elapsed = time.time() - start
        logger.info(f"Indexed {count} notes in {elapsed:.2f}s")

    def reindex_file(self, rel_path: str):
        """Re-index a single file (for incremental updates)."""
        full = self.vault_path / rel_path
        if not full.exists() or not rel_path.endswith(".md"):
            # File deleted
            if rel_path in self.notes:
                del self.notes[rel_path]
                self._tf.pop(rel_path, None)
                self._rebuild_idf()
            return

        # Skip hidden paths
        if any(part.startswith(".") for part in Path(rel_path).parts):
            return

        self._index_file(rel_path)
        self._rebuild_idf()

    def remove_file(self, rel_path: str):
        """Remove a file from the index."""
        if rel_path in self.notes:
            del self.notes[rel_path]
            self._tf.pop(rel_path, None)
            self._rebuild_idf()

    def _index_file(self, rel_path: str):
        """Parse and index a single markdown file."""
        full = self.vault_path / rel_path
        try:
            content = full.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"Cannot read {rel_path}: {e}")
            return

        stat = full.stat()
        title = Path(rel_path).stem
        tags = []
        links = []

        # Extract frontmatter tags
        fm = _FRONTMATTER_RE.match(content)
        body = content
        if fm:
            fm_text = fm.group(1)
            body = content[fm.end():]
            for line in fm_text.split("\n"):
                line = line.strip().lstrip("- ")
                if line.startswith("tags:"):
                    # tags: [a, b] or tags:\n- a\n- b
                    bracket = line.replace("tags:", "").strip()
                    if bracket.startswith("["):
                        tags.extend(t.strip().strip("'\"") for t in bracket.strip("[]").split(",") if t.strip())
                elif tags and not line.startswith(("---", "#")) and line:
                    # Continuation of tags list
                    tags.append(line.strip("'\""))

        # Extract inline #tags
        for m in _TAG_INLINE_RE.finditer(body):
            tag = m.group(1)
            if tag not in tags:
                tags.append(tag)

        # Extract [[wikilinks]]
        links = _WIKILINK_RE.findall(body)

        # Extract H1 title if available
        h1 = _H1_RE.search(body)
        if h1:
            title = h1.group(1).strip()

        # Word count
        words = self._tokenize(body)
        word_count = len(words)

        entry = NoteEntry(
            path=rel_path, title=title, tags=tags, links=links,
            word_count=word_count, modified_at=stat.st_mtime,
            content=content,
        )
        self.notes[rel_path] = entry

        # Build TF for this document
        tf = {}
        for word in words:
            tf[word] = tf.get(word, 0) + 1
        # Normalize by doc length
        if word_count > 0:
            for term in tf:
                tf[term] /= word_count
        self._tf[rel_path] = tf

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenizer: split on whitespace/punctuation, lowercase."""
        # Remove markdown formatting
        text = re.sub(r"[#*_`~\[\](){}|>]", " ", text)
        text = re.sub(r"https?://\S+", "", text)
        tokens = re.findall(r"[\w\u3040-\u9fff\u30a0-\u30ff\uff00-\uffef]+", text.lower())
        return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]

    def _rebuild_idf(self):
        """Rebuild document frequency counts."""
        self._df.clear()
        self._doc_count = len(self._tf)
        for tf_map in self._tf.values():
            for term in tf_map:
                self._df[term] = self._df.get(term, 0) + 1

    def search(self, query: str, tags: list[str] | None = None,
               path_prefix: str | None = None, max_results: int = 5) -> list[dict]:
        """TF-IDF keyword search with optional tag/path filters."""
        query_terms = self._tokenize(query)
        if not query_terms and not tags and not path_prefix:
            return []

        now = time.time()
        results = []

        for path, entry in self.notes.items():
            # Path prefix filter
            if path_prefix and not path.startswith(path_prefix):
                continue
            # Tag filter
            if tags and not any(t in entry.tags for t in tags):
                continue

            score = 0.0
            if query_terms:
                tf_map = self._tf.get(path, {})
                for term in query_terms:
                    tf = tf_map.get(term, 0)
                    df = self._df.get(term, 0)
                    if tf > 0 and df > 0 and self._doc_count > 0:
                        idf = math.log(self._doc_count / df)
                        score += tf * idf
            elif tags or path_prefix:
                score = 1.0  # tag/path filter without query

            if score <= 0 and query_terms:
                continue

            # Recent boost
            if now - entry.modified_at < RECENT_WINDOW:
                score *= RECENT_BOOST

            # Snippet: first 200 chars of body (skip frontmatter)
            body = entry.content
            fm = _FRONTMATTER_RE.match(body)
            if fm:
                body = body[fm.end():]
            snippet = body.strip()[:200]

            results.append({
                "path": path,
                "title": entry.title,
                "tags": entry.tags,
                "score": round(score, 4),
                "snippet": snippet,
                "modified_at": entry.modified_at,
                "word_count": entry.word_count,
            })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:max_results]

    def get_recent(self, limit: int = 10) -> list[dict]:
        """Return most recently modified notes."""
        sorted_notes = sorted(self.notes.values(), key=lambda n: n.modified_at, reverse=True)
        return [
            {
                "path": n.path,
                "title": n.title,
                "tags": n.tags,
                "modified_at": n.modified_at,
                "word_count": n.word_count,
            }
            for n in sorted_notes[:limit]
        ]

    def get_all_tags(self) -> dict[str, int]:
        """Return all tags with their usage counts."""
        tag_counts: dict[str, int] = {}
        for entry in self.notes.values():
            for tag in entry.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return dict(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True))

    def get_stats(self) -> dict:
        """Return index statistics."""
        return {
            "total_notes": len(self.notes),
            "indexed": len(self._tf),
            "total_tags": len(self.get_all_tags()),
            "last_change": max((n.modified_at for n in self.notes.values()), default=0),
        }
