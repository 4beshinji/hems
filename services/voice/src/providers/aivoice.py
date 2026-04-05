"""
A.I.VOICE TTS Provider — HTTP API integration (Wine/Windows host).

A.I.VOICE Editor runs on the host machine (Wine or Windows) and exposes
an HTTP API identical in structure to VOICEVOX (audio_query + synthesis).

API base: http://{host}:{port}/api/v1
Default:  http://host.docker.internal:50080/api/v1
"""
import os
import aiohttp
from loguru import logger
from tts_provider import TTSProvider, AudioResult

AIVOICE_URL = os.getenv("AIVOICE_URL", "http://host.docker.internal:50080")

# Default speaker ID mappings (tone -> speaker_id)
# Run GET /speakers to list available IDs for your voice pack.
# 結月ゆかり: 凪=0, ロボ=1, ビジネス=2, 囁き=3 (depends on installed version)
DEFAULT_SPEAKERS = {
    "neutral": 0,
    "caring": 0,
    "humorous": 0,
    "alert": 0,
    "happy": 0,
}


class AivoiceProvider(TTSProvider):
    def __init__(self, config: dict | None = None):
        self.base_url = AIVOICE_URL
        self.speakers = DEFAULT_SPEAKERS.copy()
        self.speed_scale = 1.0
        self.pitch_scale = 0.0
        self.intonation_scale = 1.0
        self.volume_scale = 1.0

        if config:
            self.base_url = config.get("url", self.base_url)
            if "speakers" in config:
                self.speakers.update(config["speakers"])
            self.speed_scale = config.get("speed_scale", self.speed_scale)
            self.pitch_scale = config.get("pitch_scale", self.pitch_scale)
            self.intonation_scale = config.get("intonation_scale", self.intonation_scale)
            self.volume_scale = config.get("volume_scale", self.volume_scale)

    @property
    def name(self) -> str:
        return "aivoice"

    @property
    def _api(self) -> str:
        return f"{self.base_url}/api/v1"

    async def synthesize(self, text: str, voice: str = "neutral", speed: float = 1.0) -> AudioResult:
        speaker_id = self.speakers.get(voice, self.speakers.get("neutral", 0))
        effective_speed = self.speed_scale * speed

        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Step 1: Generate audio query
            async with session.post(
                f"{self._api}/audio_query",
                params={"text": text, "speaker": speaker_id},
            ) as resp:
                if resp.status != 200:
                    detail = await resp.text()
                    raise Exception(f"A.I.VOICE audio_query failed: {resp.status} {detail}")
                query = await resp.json()

            query["speedScale"] = effective_speed
            query["pitchScale"] = self.pitch_scale
            query["intonationScale"] = self.intonation_scale
            query["volumeScale"] = self.volume_scale

            # Step 2: Synthesize audio → WAV bytes
            async with session.post(
                f"{self._api}/synthesis",
                params={"speaker": speaker_id},
                json=query,
            ) as resp:
                if resp.status != 200:
                    detail = await resp.text()
                    raise Exception(f"A.I.VOICE synthesis failed: {resp.status} {detail}")
                audio_data = await resp.read()

        logger.debug(f"A.I.VOICE synthesized {len(audio_data)} bytes (speaker={speaker_id})")
        return AudioResult(audio_data=audio_data, format="wav", sample_rate=24000)

    async def is_available(self) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self._api}/speakers") as resp:
                    return resp.status == 200
        except Exception:
            return False
