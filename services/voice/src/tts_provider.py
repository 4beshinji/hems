"""
TTS Provider abstract base class for HEMS Voice Service.
All TTS backends implement this interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AudioResult:
    audio_data: bytes
    format: str = "wav"  # "wav" or "mp3"
    sample_rate: int | None = None


class TTSProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        ...

    @abstractmethod
    async def synthesize(self, text: str, voice: str = "neutral", speed: float = 1.0) -> AudioResult:
        """Synthesize text to audio."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the TTS backend is reachable."""
        ...
