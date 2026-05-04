"""
STT Provider abstract base class for HEMS STT Service.
All STT backends implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TranscriptionResult:
    text: str
    language: str = "ja"
    confidence: float = 0.0
    duration_seconds: float = 0.0
    segments: list[dict] = field(default_factory=list)


class STTProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Active model name."""
        ...

    @abstractmethod
    async def transcribe(self, audio_data: bytes, language: str = "ja") -> TranscriptionResult:
        """Transcribe audio bytes to text."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the STT backend is loaded and ready."""
        ...
