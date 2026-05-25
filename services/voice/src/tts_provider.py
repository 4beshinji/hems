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
    duration: float | None = None  # seconds, set by providers that play directly


class TTSProvider(ABC):
    # Passive health monitoring opt-in. A provider that benefits from background
    # health polling sets health_poll_interval (seconds) and overrides
    # passive_health_snapshot(); the voice service runs a generic loop that polls
    # it, so no provider-specific code lives in main.py.
    health_poll_interval: float | None = None

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

    @property
    def healthy(self) -> bool:
        """Whether the backend is currently considered healthy."""
        return True

    async def passive_health_snapshot(self) -> dict | None:
        """Return a passive health status dict, or None when unsupported.

        Called periodically by the voice service when health_poll_interval is
        set. "Passive" = relies on normal synthesis traffic as an implicit
        probe rather than sending dedicated test requests.
        """
        return None
