"""
VoiSona Talk TTS Provider — REST API integration.

VoiSona Talk runs on a Windows VM and exposes a REST API.
Uses audio_device destination: audio plays directly through VM speakers
(SPICE → host audio). No file exchange needed.

API base: http://{host}:{port}/api/talk/v1
"""

import asyncio
import os
import time

import aiohttp
from loguru import logger
from tts_provider import AudioResult, TTSProvider

VOISONA_URL = os.getenv("VOISONA_URL", "http://192.168.1.173:32766")
VOISONA_USERNAME = os.getenv("VOISONA_USERNAME", "")
VOISONA_PASSWORD = os.getenv("VOISONA_PASSWORD", "")
VOISONA_VOICE = os.getenv("VOISONA_VOICE_NAME", "nurse-robot-type-t_ja_JP")
VOISONA_LANGUAGE = os.getenv("VOISONA_LANGUAGE", "ja_JP")

API_BASE = "/api/talk/v1"

# Polling settings for async synthesis
POLL_INTERVAL = 0.5  # seconds
POLL_TIMEOUT = 120.0  # seconds

# Health check settings
HEALTH_CHECK_INTERVAL = 300  # 5 minutes
HEALTH_CHECK_TEXT = "テスト"
HEALTH_SLOW_THRESHOLD = 15.0  # seconds — flag as degraded if short text takes longer


class VoisonaProvider(TTSProvider):
    def __init__(self, config: dict | None = None):
        self.base_url = VOISONA_URL
        self.username = VOISONA_USERNAME
        self.password = VOISONA_PASSWORD
        self.voice_name = VOISONA_VOICE
        self.language = VOISONA_LANGUAGE
        # Health state
        self._healthy = True
        self._last_synth_duration: float = 0.0
        self._last_health_check: float = 0.0
        self._synthesizing = False
        # Base acoustic parameters (character default)
        self._base_params: dict = {
            "speed": 1.0,
            "pitch": 0,
            "volume": 0,
            "intonation": 1.0,
            "huskiness": 0,
            "alp": 0,
        }
        # Per-tone overrides (from character YAML)
        self._tone_overrides: dict[str, dict] = {}

        if config:
            self.base_url = config.get("url", self.base_url)
            self.username = config.get("username", self.username)
            self.password = config.get("password", self.password)
            self.voice_name = config.get("voice_name", self.voice_name)
            self.language = config.get("language", self.language)
            # Read base acoustic params from character config
            for key in list(self._base_params):
                if key in config:
                    self._base_params[key] = config[key]
            # Read tone overrides
            for tone_name, tone_cfg in config.get("tones", {}).items():
                if isinstance(tone_cfg, dict):
                    self._tone_overrides[tone_name] = tone_cfg

    @property
    def name(self) -> str:
        return "voisona"

    @property
    def healthy(self) -> bool:
        return self._healthy

    def _auth(self) -> aiohttp.BasicAuth:
        return aiohttp.BasicAuth(self.username, self.password)

    @property
    def _api_url(self) -> str:
        return f"{self.base_url}{API_BASE}"

    def _build_params(self, tone: str, speed_override: float) -> dict:
        """Build global_parameters by merging base + tone-specific overrides."""
        params = dict(self._base_params)  # copy base

        # Apply tone-specific overrides
        if tone in self._tone_overrides:
            override = self._tone_overrides[tone]
            for key in ("speed", "pitch", "volume", "intonation", "huskiness", "alp"):
                if key in override and override[key] is not None:
                    params[key] = override[key]
            if "style_weights" in override:
                params["style_weights"] = override["style_weights"]

        # Apply runtime speed multiplier
        if speed_override != 1.0:
            params["speed"] = params["speed"] * speed_override

        # Clamp to API limits
        params["speed"] = max(0.2, min(5.0, params["speed"]))
        params["pitch"] = max(-600, min(600, params["pitch"]))
        params["volume"] = max(-8, min(8, params["volume"]))
        params["intonation"] = max(0, min(2, params["intonation"]))
        params["huskiness"] = max(-20, min(20, params["huskiness"]))
        params["alp"] = max(-1, min(1, params["alp"]))

        # Remove defaults to keep request minimal
        defaults = {"speed": 1.0, "pitch": 0, "volume": 0, "intonation": 1.0, "huskiness": 0, "alp": 0}
        return {k: v for k, v in params.items() if k == "style_weights" or v != defaults.get(k)}

    async def synthesize(self, text: str, voice: str = "neutral", speed: float = 1.0) -> AudioResult:
        global_params = self._build_params(voice, speed)

        body: dict = {
            "language": self.language,
            "text": text,
            "voice_name": self.voice_name,
            "force_enqueue": True,
        }
        if global_params:
            body["global_parameters"] = global_params

        logger.debug(f"VoiSona synthesize: tone={voice}, params={global_params}")

        self._synthesizing = True
        wall_start = time.monotonic()
        timeout = aiohttp.ClientTimeout(total=POLL_TIMEOUT + 10)
        try:
            return await self._do_synthesize(body, wall_start, timeout)
        finally:
            self._synthesizing = False

    async def _do_synthesize(self, body: dict, wall_start: float, timeout: aiohttp.ClientTimeout) -> AudioResult:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # POST synthesis request
            async with session.post(
                f"{self._api_url}/speech-syntheses",
                json=body,
                auth=self._auth(),
            ) as resp:
                if resp.status != 201:
                    detail = await resp.text()
                    raise Exception(f"VoiSona speech-syntheses POST failed: {resp.status} {detail}")
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
                            wall_elapsed = time.monotonic() - wall_start
                            self._last_synth_duration = wall_elapsed
                            self._healthy = True
                            logger.info(f"VoiSona synthesis complete: {duration:.2f}s (wall {wall_elapsed:.1f}s)")
                            break
                        if state == "failed":
                            raise Exception(f"VoiSona synthesis failed: {status}")
                await asyncio.sleep(POLL_INTERVAL)
                elapsed += POLL_INTERVAL
            else:
                self._healthy = False
                raise Exception(f"VoiSona synthesis timed out after {POLL_TIMEOUT}s")

        # audio_device mode: audio played directly through VM, no bytes to return
        return AudioResult(audio_data=b"", format="wav", duration=duration)

    async def is_available(self) -> bool:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.get(
                    f"{self._api_url}/voices",
                    auth=self._auth(),
                ) as resp,
            ):
                return resp.status == 200
        except Exception:
            return False

    async def health_check(self) -> dict:
        """Run a probe synthesis to measure VoiSona responsiveness.

        Returns dict with keys: healthy, wall_seconds, state, detail.
        """
        self._last_health_check = time.monotonic()

        # Skip if a real synthesis is in progress (would queue behind it)
        if self._synthesizing:
            return {"healthy": self._healthy, "wall_seconds": 0, "state": "skipped", "detail": "Synthesis in progress"}

        # 1. API reachable?
        if not await self.is_available():
            self._healthy = False
            return {"healthy": False, "wall_seconds": 0, "state": "unreachable", "detail": "VoiSona API unreachable"}

        # 2. Submit a short probe synthesis
        body = {
            "language": self.language,
            "text": HEALTH_CHECK_TEXT,
            "voice_name": self.voice_name,
            "force_enqueue": True,
        }
        wall_start = time.monotonic()
        try:
            timeout = aiohttp.ClientTimeout(total=HEALTH_SLOW_THRESHOLD + 5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self._api_url}/speech-syntheses",
                    json=body,
                    auth=self._auth(),
                ) as resp:
                    if resp.status != 201:
                        self._healthy = False
                        return {
                            "healthy": False,
                            "wall_seconds": 0,
                            "state": "post_failed",
                            "detail": f"POST status {resp.status}",
                        }
                    result = await resp.json()

                synth_uuid = result["uuid"]
                elapsed = 0.0
                while elapsed < HEALTH_SLOW_THRESHOLD:
                    async with session.get(
                        f"{self._api_url}/speech-syntheses/{synth_uuid}",
                        auth=self._auth(),
                    ) as resp:
                        if resp.status == 200:
                            status = await resp.json()
                            state = status.get("state")
                            if state == "succeeded":
                                wall = time.monotonic() - wall_start
                                self._healthy = True
                                return {"healthy": True, "wall_seconds": round(wall, 2), "state": "ok", "detail": ""}
                            if state == "failed":
                                self._healthy = False
                                return {
                                    "healthy": False,
                                    "wall_seconds": 0,
                                    "state": "synthesis_failed",
                                    "detail": str(status),
                                }
                    await asyncio.sleep(0.5)
                    elapsed += 0.5

                # Timed out — degraded
                wall = time.monotonic() - wall_start
                self._healthy = False
                return {
                    "healthy": False,
                    "wall_seconds": round(wall, 2),
                    "state": "slow",
                    "detail": f"Probe took >{HEALTH_SLOW_THRESHOLD}s — VoiSona likely degraded",
                }
        except Exception as e:
            self._healthy = False
            return {"healthy": False, "wall_seconds": 0, "state": "error", "detail": str(e)}
