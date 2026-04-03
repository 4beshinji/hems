"""
HTML loader — .html/.htm files with tag stripping via BeautifulSoup.
"""
from pathlib import Path
from loguru import logger

from .base import BaseLoader, DocumentEntry

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False
    logger.warning("beautifulsoup4 not installed — HTML loading disabled")


class HtmlLoader(BaseLoader):
    extensions = [".html", ".htm"]
    doc_type = "html"

    def load(self, file_path: Path, rel_path: str, source_name: str) -> DocumentEntry | None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"Cannot read {rel_path}: {e}")
            return None

        stat = file_path.stat()
        title = Path(rel_path).stem
        tags = ["html"]
        metadata: dict = {}

        if not _HAS_BS4:
            # Fallback: simple tag stripping
            import re
            body = re.sub(r"<[^>]+>", " ", content)
            body = re.sub(r"\s+", " ", body).strip()
        else:
            soup = BeautifulSoup(content, "html.parser")

            # Extract title
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                title = title_tag.string.strip()

            # Extract meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                metadata["description"] = meta_desc["content"]

            # Remove script and style elements
            for tag in soup(["script", "style"]):
                tag.decompose()

            body = soup.get_text(separator="\n", strip=True)

        return DocumentEntry(
            path=rel_path, source_name=source_name, title=title,
            doc_type=self.doc_type, tags=tags, metadata=metadata,
            word_count=len(body.split()), modified_at=stat.st_mtime,
            content=content, body=body,
        )
