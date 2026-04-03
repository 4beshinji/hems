"""
PDF loader — .pdf files via pdfplumber text extraction.
"""
from pathlib import Path
from loguru import logger

from .base import BaseLoader, DocumentEntry

try:
    import pdfplumber
    _HAS_PDFPLUMBER = True
except ImportError:
    _HAS_PDFPLUMBER = False
    logger.warning("pdfplumber not installed — PDF loading disabled")

MAX_PAGES = 200


class PdfLoader(BaseLoader):
    extensions = [".pdf"]
    doc_type = "pdf"

    def load(self, file_path: Path, rel_path: str, source_name: str) -> DocumentEntry | None:
        if not _HAS_PDFPLUMBER:
            return None

        stat = file_path.stat()
        title = Path(rel_path).stem
        tags = ["pdf"]
        metadata: dict = {}

        try:
            with pdfplumber.open(file_path) as pdf:
                metadata["pages"] = len(pdf.pages)
                pages_text = []
                for i, page in enumerate(pdf.pages[:MAX_PAGES]):
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)

                body = "\n\n".join(pages_text)
                # Try to extract title from first page
                if pages_text:
                    first_lines = pages_text[0].split("\n")
                    for line in first_lines[:5]:
                        line = line.strip()
                        if len(line) > 5 and len(line) < 200:
                            title = line
                            break
        except Exception as e:
            logger.warning(f"PDF extraction failed for {rel_path}: {e}")
            return None

        return DocumentEntry(
            path=rel_path, source_name=source_name, title=title,
            doc_type=self.doc_type, tags=tags, metadata=metadata,
            word_count=len(body.split()), modified_at=stat.st_mtime,
            content=f"[PDF: {metadata.get('pages', '?')} pages]\n{body[:500]}...",
            body=body,
        )
