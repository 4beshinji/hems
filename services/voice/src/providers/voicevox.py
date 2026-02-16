"""
VOICEVOX TTS Provider — Docker-based Japanese speech synthesis.
"""
import os
import aiohttp
from loguru import logger
from tts_provider import TTSProvider, AudioResult

VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://voicevox:50021")

# Default speaker mappings (tone -> speaker_id)
DEFAULT_SPEAKERS = {
    "neutral": 47,
    "caring": 47,
    "humorous": 48,
    "alert": 46,
    "happy": 47,
}


class VoicevoxProvider(TTSProvider):
    def __init__(self, config: dict = None):
        self.base_url = config.get("url", VOICEVOX_URL) if config else VOICEVOX_URL
        self.speakers = DEFAULT_SPEAKERS.copy()
        self.speed_scale = 1.0
        self.pitch_scale = 0.0
        self.intonation_scale = 1.0

        if config:
            speakers = config.get("speakers", {})
            if speakers:
                self.speakers.update(speakers)
            self.speed_scale = config.get("speed_scale", 1.0)
            self.pitch_scale = config.get("pitch_scale", 0.0)
            self.intonation_scale = config.get("intonation_scale", 1.0)

    @property
    def name(self) -> str:
        return "voicevox"

    async def synthesize(self, text: str, voice: str = "neutral", speed: float = 1.0) -> AudioResult:
        speaker_id = self.speakers.get(voice, self.speakers.get("neutral", 47))
        effective_speed = self.speed_scale * speed

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            # Step 1: Generate audio query
            async with session.post(
                f"{self.base_url}/audio_query",
                params={"text": text, "speaker": speaker_id},
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"VOICEVOX audio_query failed: {resp.status}")
                query = await resp.json()

            query["speedScale"] = effective_speed
            query["pitchScale"] = self.pitch_scale
            query["intonationScale"] = self.intonation_scale

            # Step 2: Synthesize audio
            async with session.post(
                f"{self.base_url}/synthesis",
                params={"speaker": speaker_id},
                json=query,
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"VOICEVOX synthesis failed: {resp.status}")
                audio_data = await resp.read()

        return AudioResult(audio_data=audio_data, format="wav", sample_rate=24000)

    async def is_available(self) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.base_url}/speakers") as resp:
                    return resp.status == 200
        except Exception:
            return False
