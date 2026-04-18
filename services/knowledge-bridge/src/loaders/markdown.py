"""
Markdown loader — .md files with YAML frontmatter, inline tags, wikilinks.
Ported from obsidian-bridge vault_index.py.
"""

import re
from pathlib import Path

from loguru import logger

from .base import BaseLoader, DocumentEntry

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_TAG_INLINE_RE = re.compile(r"(?:^|\s)#([a-zA-Z0-9_/\u3040-\u9fff-]+)", re.UNICODE)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


class MarkdownLoader(BaseLoader):
    extensions = [".md"]
    doc_type = "markdown"

    def load(self, file_path: Path, rel_path: str, source_name: str) -> DocumentEntry | None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"Cannot read {rel_path}: {e}")
            return None

        stat = file_path.stat()
        title = Path(rel_path).stem
        tags = []
        metadata = {}

        # Extract frontmatter
        fm = _FRONTMATTER_RE.match(content)
        body = content
        if fm:
            fm_text = fm.group(1)
            body = content[fm.end() :]
            for line in fm_text.split("\n"):
                line_stripped = line.strip().lstrip("- ")
                if line_stripped.startswith("tags:"):
                    bracket = line_stripped.replace("tags:", "").strip()
                    if bracket.startswith("["):
                        tags.extend(t.strip().strip("'\"") for t in bracket.strip("[]").split(",") if t.strip())
                elif tags and not line_stripped.startswith(("---", "#")) and line_stripped:
                    tags.append(line_stripped.strip("'\""))
                # Extract common metadata fields
                for key in ("title", "authors", "year", "venue", "doi", "s2_id", "citation_count"):
                    if line_stripped.startswith(f"{key}:"):
                        val = line_stripped.split(":", 1)[1].strip().strip("'\"")
                        if val:
                            metadata[key] = val
            if "title" in metadata:
                title = metadata["title"]

        # Extract inline #tags
        for m in _TAG_INLINE_RE.finditer(body):
            tag = m.group(1)
            if tag not in tags:
                tags.append(tag)

        # Extract [[wikilinks]]
        links = _WIKILINK_RE.findall(body)
        if links:
            metadata["links"] = links

        # Extract H1 title if available and no frontmatter title
        if "title" not in metadata:
            h1 = _H1_RE.search(body)
            if h1:
                title = h1.group(1).strip()

        return DocumentEntry(
            path=rel_path,
            source_name=source_name,
            title=title,
            doc_type=self.doc_type,
            tags=tags,
            metadata=metadata,
            word_count=len(body.split()),
            modified_at=stat.st_mtime,
            content=content,
            body=body,
        )
