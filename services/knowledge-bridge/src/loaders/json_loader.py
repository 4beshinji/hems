"""
JSON loader — .json files with structured data flattening for search.
"""
import json
from pathlib import Path
from loguru import logger

from .base import BaseLoader, DocumentEntry

MAX_BODY_LENGTH = 10000
MAX_FLATTEN_DEPTH = 3


def _flatten(obj, prefix: str = "", depth: int = 0) -> list[str]:
    """Flatten nested JSON into searchable key: value pairs."""
    if depth >= MAX_FLATTEN_DEPTH:
        return [f"{prefix}: {str(obj)[:200]}"] if prefix else [str(obj)[:200]]

    parts = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            parts.extend(_flatten(v, key, depth + 1))
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:50]):  # limit array items
            parts.extend(_flatten(item, f"{prefix}[{i}]", depth + 1))
    else:
        val = str(obj)
        if val and prefix:
            parts.append(f"{prefix}: {val}")
        elif val:
            parts.append(val)
    return parts


class JsonLoader(BaseLoader):
    extensions = [".json"]
    doc_type = "json"

    def load(self, file_path: Path, rel_path: str, source_name: str) -> DocumentEntry | None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"Cannot read {rel_path}: {e}")
            return None

        stat = file_path.stat()
        title = Path(rel_path).stem
        tags = ["json"]
        metadata: dict = {}

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return DocumentEntry(
                path=rel_path, source_name=source_name, title=title,
                doc_type=self.doc_type, tags=tags, metadata=metadata,
                word_count=len(content.split()), modified_at=stat.st_mtime,
                content=content, body=content[:MAX_BODY_LENGTH],
            )

        # Extract summary metadata
        if isinstance(data, dict):
            if "title" in data:
                title = str(data["title"])
            metadata["keys"] = list(data.keys())[:20]
            metadata["type"] = "object"
        elif isinstance(data, list):
            metadata["type"] = "array"
            metadata["length"] = len(data)

        # Flatten for search
        flat_parts = _flatten(data)
        body = "\n".join(flat_parts)
        if len(body) > MAX_BODY_LENGTH:
            body = body[:MAX_BODY_LENGTH]

        return DocumentEntry(
            path=rel_path, source_name=source_name, title=title,
            doc_type=self.doc_type, tags=tags, metadata=metadata,
            word_count=len(body.split()), modified_at=stat.st_mtime,
            content=content, body=body,
        )
