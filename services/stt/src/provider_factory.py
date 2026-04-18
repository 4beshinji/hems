"""
STT Provider factory -- creates the appropriate provider based on config.
"""

import os

from loguru import logger
from stt_provider import STTProvider

# Providers that can be instantiated (checked at runtime)
_AVAILABLE_PROVIDERS: list[str] = []


def _detect_available() -> list[str]:
    """Detect which provider packages are installed."""
    available = []
    try:
        import faster_whisper  # noqa: F401

        available.append("whisper")
    except ImportError:
        pass
    try:
        import sherpa_onnx  # noqa: F401

        available.append("sherpa-onnx")
    except ImportError:
        pass
    try:
        import qwen_asr  # noqa: F401

        available.append("qwen3-asr")
    except ImportError:
        pass
    return available


def get_available_providers() -> list[str]:
    global _AVAILABLE_PROVIDERS
    if not _AVAILABLE_PROVIDERS:
        _AVAILABLE_PROVIDERS = _detect_available()
    return _AVAILABLE_PROVIDERS


def create_provider() -> STTProvider:
    """Create STT provider based on STT_PROVIDER env var."""
    provider_name = os.getenv("STT_PROVIDER", "whisper")
    logger.info(f"Creating STT provider: {provider_name}")

    if provider_name == "whisper":
        from providers.whisper import WhisperProvider

        return WhisperProvider()
    elif provider_name == "sherpa-onnx":
        from providers.sherpa_onnx import SherpaOnnxProvider

        return SherpaOnnxProvider()
    elif provider_name == "qwen3-asr":
        from providers.qwen3_asr import Qwen3AsrProvider

        return Qwen3AsrProvider()
    else:
        logger.warning(f"Unknown STT provider '{provider_name}', falling back to whisper")
        from providers.whisper import WhisperProvider

        return WhisperProvider()
