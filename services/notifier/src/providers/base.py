"""
HEMS Lite Notifier — provider base class.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Notification:
    level: str       # CRITICAL | HIGH | NORMAL | INFO
    title: str
    body: str
    source: str = ""
    zone: str = ""
    site_id: str = ""
    site_name: str = ""
    timestamp: float = 0.0


class NotifyProvider(ABC):
    """Abstract notification provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def send(self, notification: Notification) -> bool:
        """Send notification. Returns True on success."""
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider has valid configuration."""
        ...
