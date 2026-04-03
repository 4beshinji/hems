"""
CSV loader — .csv files with header + row text extraction.
"""
import csv
import io
from pathlib import Path
from loguru import logger

from .base import BaseLoader, DocumentEntry

MAX_ROWS = 100


class CsvLoader(BaseLoader):
    extensions = [".csv"]
    doc_type = "csv"

    def load(self, file_path: Path, rel_path: str, source_name: str) -> DocumentEntry | None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"Cannot read {rel_path}: {e}")
            return None

        stat = file_path.stat()
        title = Path(rel_path).stem
        tags = ["csv"]
        metadata: dict = {}

        try:
            reader = csv.reader(io.StringIO(content))
            rows = list(reader)
        except csv.Error:
            return DocumentEntry(
                path=rel_path, source_name=source_name, title=title,
                doc_type=self.doc_type, tags=tags, metadata=metadata,
                word_count=len(content.split()), modified_at=stat.st_mtime,
                content=content, body=content[:5000],
            )

        if not rows:
            return None

        headers = rows[0]
        metadata["columns"] = headers
        metadata["rows"] = len(rows) - 1

        # Build searchable text: header labels + sample rows
        body_parts = [" ".join(headers)]
        for row in rows[1:MAX_ROWS + 1]:
            row_text = " ".join(f"{h}: {v}" for h, v in zip(headers, row) if v.strip())
            if row_text:
                body_parts.append(row_text)

        body = "\n".join(body_parts)

        return DocumentEntry(
            path=rel_path, source_name=source_name, title=title,
            doc_type=self.doc_type, tags=tags, metadata=metadata,
            word_count=len(body.split()), modified_at=stat.st_mtime,
            content=content, body=body,
        )
