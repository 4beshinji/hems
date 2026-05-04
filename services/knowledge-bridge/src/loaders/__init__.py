"""
Loader registry — auto-detect document type by file extension.
"""

from pathlib import Path

from .base import BaseLoader, DocumentEntry
from .csv_loader import CsvLoader
from .docx import DocxLoader
from .html_loader import HtmlLoader
from .json_loader import JsonLoader
from .markdown import MarkdownLoader
from .pdf import PdfLoader
from .python_loader import PythonLoader
from .text import TextLoader

_LOADERS: dict[str, BaseLoader] = {}
_text_loader = TextLoader()


def register_loader(loader: BaseLoader):
    for ext in loader.extensions:
        _LOADERS[ext] = loader


def get_loader(file_path: Path) -> BaseLoader:
    """Get the appropriate loader for a file extension."""
    return _LOADERS.get(file_path.suffix.lower(), _text_loader)


def get_supported_extensions() -> list[str]:
    """Return all registered extensions."""
    return list(_LOADERS.keys())


# Auto-register all loaders
register_loader(MarkdownLoader())
register_loader(PythonLoader())
register_loader(JsonLoader())
register_loader(_text_loader)
register_loader(PdfLoader())
register_loader(DocxLoader())
register_loader(CsvLoader())
register_loader(HtmlLoader())

__all__ = ["BaseLoader", "DocumentEntry", "get_loader", "get_supported_extensions"]
