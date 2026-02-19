"""
Abstract base class for biometric data providers.
"""
from abc import ABC, abstractmethod
from data_processor import BiometricReading


class BiometricProvider(ABC):
    """Base class for biometric data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'gadgetbridge', 'zepp')."""
        ...

    @abstractmethod
    async def start(self):
        """Start the provider (connect, begin polling, etc.)."""
        ...

    @abstractmethod
    async def stop(self):
        """Stop the provider."""
        ...

    @abstractmethod
    async def get_latest(self) -> BiometricReading | None:
        """Get the latest reading from this provider."""
        ...
