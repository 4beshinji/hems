"""
Zepp Cloud API provider — polls historical biometric data from Zepp/Huami cloud.
Optional supplementary provider for batch sleep/activity data.
"""
import time
from loguru import logger
from data_processor import BiometricReading
from providers.base import BiometricProvider


class ZeppProvider(BiometricProvider):
    """Polls Zepp Cloud API for historical biometric data (batch, not real-time)."""

    def __init__(self, email: str = "", password: str = "", poll_interval: int = 1800):
        self._email = email
        self._password = password
        self._poll_interval = poll_interval
        self._latest: BiometricReading | None = None
        self._running = False

    @property
    def name(self) -> str:
        return "zepp"

    async def start(self):
        if not self._email or not self._password:
            logger.info("Zepp provider disabled (no credentials)")
            return
        self._running = True
        logger.info("Zepp provider started (polling mode)")

    async def stop(self):
        self._running = False

    async def get_latest(self) -> BiometricReading | None:
        return self._latest

    async def poll(self) -> BiometricReading | None:
        """Poll Zepp API for latest data. Returns None if not configured."""
        if not self._running:
            return None
        # Placeholder: Zepp API integration is optional and reverse-engineered.
        # Implementation would go here when needed.
        logger.debug("Zepp poll: not implemented (placeholder)")
        return None
