"""
TTS Provider factory — creates the appropriate provider based on config.
"""
import os
from loguru import logger
from tts_provider import TTSProvider


def create_provider(character_config: dict = None) -> TTSProvider:
    """Create TTS provider based on env and character config."""
    provider_name = os.getenv("TTS_PROVIDER", "voicevox")

    # Character config can override provider
    if character_config:
        voice_cfg = character_config.get("voice", {})
        if voice_cfg.get("backend"):
            provider_name = voice_cfg["backend"]

    voice_config = {}
    if character_config:
        voice_cfg = character_config.get("voice", {})
        provider_config = voice_cfg.get(provider_name, {})
        voice_config = provider_config

    logger.info(f"Creating TTS provider: {provider_name}")

    if provider_name == "voicevox":
        from providers.voicevox import VoicevoxProvider
        return VoicevoxProvider(config=voice_config)
    elif provider_name == "espeak":
        from providers.espeak import EspeakProvider
        return EspeakProvider(config=voice_config)
    elif provider_name == "edge-tts":
        from providers.edge_tts_provider import EdgeTTSProvider
        return EdgeTTSProvider(config=voice_config)
    else:
        logger.warning(f"Unknown TTS provider '{provider_name}', falling back to espeak")
        from providers.espeak import EspeakProvider
        return EspeakProvider()
