"""
TTS Provider factory — creates the appropriate provider based on config.

Supports an optional fallback provider via TTS_FALLBACK env var or
character YAML ``voice.fallback``. When configured, the primary provider
is wrapped in FallbackProvider so synthesis automatically retries on the
fallback backend if the primary fails.
"""

import os

from loguru import logger
from tts_provider import TTSProvider

_PROVIDERS = {
    "voicevox": ("providers.voicevox", "VoicevoxProvider"),
    "espeak": ("providers.espeak", "EspeakProvider"),
    "edge-tts": ("providers.edge_tts_provider", "EdgeTTSProvider"),
    "voisona": ("providers.voisona", "VoisonaProvider"),
    "aivoice": ("providers.aivoice", "AivoiceProvider"),
}


def _instantiate(name: str, config: dict) -> TTSProvider | None:
    """Import and instantiate a provider by name. Returns None if unknown."""
    entry = _PROVIDERS.get(name)
    if entry is None:
        return None
    module_name, class_name = entry
    import importlib

    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    return cls(config=config)


def _voice_config_for(provider_name: str, character_config: dict | None) -> dict:
    if not character_config:
        return {}
    return character_config.get("voice", {}).get(provider_name, {})


def create_provider(character_config: dict | None = None) -> TTSProvider:
    """Create TTS provider based on env and character config."""
    provider_name = os.getenv("TTS_PROVIDER", "voicevox")

    # Character config can override provider
    if character_config:
        voice_cfg = character_config.get("voice", {})
        if voice_cfg.get("backend"):
            provider_name = voice_cfg["backend"]

    voice_config = _voice_config_for(provider_name, character_config)

    logger.info("Creating TTS provider: {}", provider_name)

    primary = _instantiate(provider_name, voice_config)
    if primary is None:
        logger.warning("Unknown TTS provider '{}', falling back to espeak", provider_name)
        from providers.espeak import EspeakProvider

        return EspeakProvider()

    # --- Fallback provider ---
    fallback_name = os.getenv("TTS_FALLBACK", "")
    if character_config:
        fb = character_config.get("voice", {}).get("fallback")
        if fb:
            fallback_name = fb

    if fallback_name and fallback_name != provider_name:
        fb_config = _voice_config_for(fallback_name, character_config)
        fallback = _instantiate(fallback_name, fb_config)
        if fallback:
            from providers.fallback import FallbackProvider

            logger.info("Fallback TTS: {} -> {}", provider_name, fallback_name)
            return FallbackProvider(primary, fallback)
        else:
            logger.warning("Unknown fallback TTS '{}', ignoring", fallback_name)

    return primary
