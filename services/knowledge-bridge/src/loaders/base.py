"""
Base loader — DocumentEntry dataclass and BaseLoader ABC.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DocumentEntry:
    path: str            # relative to source root
    source_name: str     # source config name (e.g., "pws")
    title: str
    doc_type: str        # "markdown", "python", "json", "text", "pdf", "docx", "csv", "html"
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    word_count: int = 0
    modified_at: float = 0
    content: str = ""    # raw content (returned on read)
    body: str = ""       # searchable text (TF-IDF target)


class BaseLoader(ABC):
    """Abstract base for document loaders."""
    extensions: list[str] = []
    doc_type: str = "unknown"

    @abstractmethod
    def load(self, file_path: Path, rel_path: str, source_name: str) -> DocumentEntry | None:
        """Load a file and return a DocumentEntry, or None on failure."""
        ...
