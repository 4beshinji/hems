"""
VoiSona Talk TTS Provider — REST API integration.

VoiSona Talk runs on a Windows VM and exposes a REST API.
Uses audio_device destination: audio plays directly through VM speakers
(SPICE → host audio). No file exchange needed.

API base: http://{host}:{port}/api/talk/v1
"""
import asyncio
import os

import aiohttp
from loguru import logger
from tts_provider import TTSProvider, AudioResult

VOISONA_URL = os.getenv("VOISONA_URL", "http://192.168.1.173:32766")
VOISONA_USERNAME = os.getenv("VOISONA_USERNAME", "")
VOISONA_PASSWORD = os.getenv("VOISONA_PASSWORD", "")
VOISONA_VOICE = os.getenv("VOISONA_VOICE_NAME", "nurse-robot-type-t_ja_JP")
VOISONA_LANGUAGE = os.getenv("VOISONA_LANGUAGE", "ja_JP")

API_BASE = "/api/talk/v1"

# Polling settings for async synthesis
POLL_INTERVAL = 0.3  # seconds
POLL_TIMEOUT = 30.0  # seconds


class VoisonaProvider(TTSProvider):
    def __init__(self, config: dict | None = None):
        self.base_url = VOISONA_URL
        self.username = VOISONA_USERNAME
        self.password = VOISONA_PASSWORD
        self.voice_name = VOISONA_VOICE
        self.language = VOISONA_LANGUAGE

        if config:
            self.base_url = config.get("url", self.base_url)
            self.username = config.get("username", self.username)
            self.password = config.get("password", self.password)
            self.voice_name = config.get("voice_name", self.voice_name)
            self.language = config.get("language", self.language)

    @property
    def name(self) -> str:
        return "voisona"

    def _auth(self) -> aiohttp.BasicAuth:
        return aiohttp.BasicAuth(self.username, self.password)

    @property
    def _api_url(self) -> str:
        return f"{self.base_url}{API_BASE}"

    async def synthesize(
        self, text: str, voice: str = "neutral", speed: float = 1.0
    ) -> AudioResult:
        body: dict = {
            "language": self.language,
            "text": text,
            "voice_name": self.voice_name,
            "force_enqueue": True,
            # audio_device is the default — plays through VM speakers
        }

        global_params: dict = {}
        if speed != 1.0:
            global_params["speed"] = max(0.2, min(5.0, speed))
        if global_params:
            body["global_parameters"] = global_params

        timeout = aiohttp.ClientTimeout(total=POLL_TIMEOUT + 10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # POST synthesis request
            async with session.post(
                f"{self._api_url}/speech-syntheses",
                json=body,
                auth=self._auth(),
            ) as resp:
                if resp.status != 201:
                    detail = await resp.text()
                    raise Exception(
                        f"VoiSona speech-syntheses POST failed: {resp.status} {detail}"
                    )
                result = await resp.json()

            synth_uuid = result["uuid"]
            logger.debug(f"VoiSona synthesis started: {synth_uuid}")

            # Poll until completion
            duration = 0.0
            elapsed = 0.0
            while elapsed < POLL_TIMEOUT:
                async with session.get(
                    f"{self._api_url}/speech-syntheses/{synth_uuid}",
                    auth=self._auth(),
                ) as resp:
                    if resp.status == 200:
                        status = await resp.json()
                        state = status.get("state")
                        if state == "succeeded":
                            duration = status.get("duration", 0.0)
                            logger.info(
                                f"VoiSona synthesis complete: {duration:.2f}s"
                            )
                            break
                        if state == "failed":
                            raise Exception(
                                f"VoiSona synthesis failed: {status}"
                            )
                await asyncio.sleep(POLL_INTERVAL)
                elapsed += POLL_INTERVAL
            else:
                raise Exception(
                    f"VoiSona synthesis timed out after {POLL_TIMEOUT}s"
                )

        # audio_device mode: audio played directly through VM, no bytes to return
        return AudioResult(audio_data=b"", format="wav", duration=duration)

    async def is_available(self) -> bool:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self._api_url}/voices",
                    auth=self._auth(),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
