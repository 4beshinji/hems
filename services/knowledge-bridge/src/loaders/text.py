"""
Text loader — fallback for .txt, .yaml, .yml, .toml, .rst, .cfg files.
"""

from pathlib import Path

from loguru import logger

from .base import BaseLoader, DocumentEntry


class TextLoader(BaseLoader):
    extensions = [".txt", ".yaml", ".yml", ".toml", ".rst", ".cfg", ".ini", ".env"]
    doc_type = "text"

    def load(self, file_path: Path, rel_path: str, source_name: str) -> DocumentEntry | None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"Cannot read {rel_path}: {e}")
            return None

        stat = file_path.stat()
        title = Path(rel_path).stem

        return DocumentEntry(
            path=rel_path,
            source_name=source_name,
            title=title,
            doc_type=self.doc_type,
            tags=[],
            word_count=len(content.split()),
            modified_at=stat.st_mtime,
            content=content,
            body=content,
        )
