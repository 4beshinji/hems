"""
Fallback TTS Provider — tries primary, falls back on failure.

Wraps two TTSProvider instances. On synthesize(), tries primary first;
if it raises any exception, logs a warning and delegates to fallback.
"""

from loguru import logger
from tts_provider import AudioResult, TTSProvider


class FallbackProvider(TTSProvider):
    def __init__(self, primary: TTSProvider, fallback: TTSProvider):
        self.primary = primary
        self.fallback = fallback
        self._using_fallback = False

    @property
    def name(self) -> str:
        return f"{self.primary.name}+{self.fallback.name}"

    async def synthesize(self, text: str, voice: str = "neutral", speed: float = 1.0) -> AudioResult:
        try:
            result = await self.primary.synthesize(text, voice=voice, speed=speed)
            if self._using_fallback:
                logger.info("Primary TTS ({}) recovered", self.primary.name)
                self._using_fallback = False
            return result
        except Exception as e:
            if not self._using_fallback:
                logger.warning("Primary TTS ({}) failed: {}. Switching to {}", self.primary.name, e, self.fallback.name)
                self._using_fallback = True
            return await self.fallback.synthesize(text, voice=voice, speed=speed)

    async def is_available(self) -> bool:
        if await self.primary.is_available():
            return True
        return await self.fallback.is_available()

    # Health monitoring tracks the primary provider (the one we prefer to use).
    @property
    def health_poll_interval(self) -> float | None:
        return self.primary.health_poll_interval

    @property
    def healthy(self) -> bool:
        return self.primary.healthy

    async def passive_health_snapshot(self) -> dict | None:
        return await self.primary.passive_health_snapshot()
