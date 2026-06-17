"""
HTTP transport layer for DashboardClient.

Wraps aiohttp session calls with auth headers and uniform error handling.
All URL construction, header injection (backend_auth_headers / internal
headers), and timeout constants live here.  Domain logic and payload
serialisation live in dashboard_mappers.py; the public facade lives in
dashboard_client.py.
"""

import os

from loguru import logger

from brain_constants import backend_auth_headers, brain_auth_headers

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
VOICE_SERVICE_URL = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")


class DashboardTransport:
    """Low-level HTTP client: one method per endpoint family."""

    def __init__(self, session, backend_url: str, voice_url: str) -> None:
        self.session = session
        self.backend_url = backend_url
        self.voice_url = voice_url

    # ------------------------------------------------------------------
    # Backend snapshot push helpers
    # ------------------------------------------------------------------

    async def post_snapshot(self, path: str, payload: dict, *, timeout: int = 5) -> bool:
        """POST payload to ``{backend_url}{path}``.

        Returns True on HTTP 200, False otherwise (errors logged at DEBUG).
        """
        url = f"{self.backend_url}{path}"
        try:
            async with self.session.post(
                url,
                headers=backend_auth_headers(),
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status == 200:
                    return True
                logger.debug(f"Snapshot push {path} failed: {resp.status}")
                return False
        except Exception as e:
            logger.debug(f"Snapshot push {path} error: {e}")
            return False

    async def post_snapshot_multi_status(
        self, path: str, payload: dict, ok_statuses: tuple = (200, 201), *, timeout: int = 5
    ) -> bool:
        """POST payload accepting multiple OK status codes (e.g. 200 or 201)."""
        url = f"{self.backend_url}{path}"
        try:
            async with self.session.post(
                url,
                headers=backend_auth_headers(),
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status in ok_statuses:
                    return True
                logger.debug(f"POST {path} failed: {resp.status}")
                return False
        except Exception as e:
            logger.debug(f"POST {path} error: {e}")
            return False

    async def post_and_return_json(self, path: str, payload: dict, *, timeout: int = 5) -> dict | None:
        """POST payload and return parsed JSON body on HTTP 200, else None."""
        url = f"{self.backend_url}{path}"
        try:
            async with self.session.post(
                url,
                headers=backend_auth_headers(),
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                text = await resp.text()
                logger.warning(f"POST {path} failed: {resp.status} {text[:200]}")
        except Exception as e:
            logger.error(f"POST {path} error: {e}")
        return None

    async def get_json(self, path: str, *, params: dict | None = None, timeout: int = 5) -> list | dict | None:
        """GET from ``{backend_url}{path}`` and return parsed JSON on HTTP 200."""
        url = f"{self.backend_url}{path}"
        try:
            async with self.session.get(
                url,
                headers=backend_auth_headers(),
                params=params,
                timeout=timeout,
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning(f"GET {path} failed: {resp.status}")
        except Exception as e:
            logger.warning(f"GET {path} error: {e}")
        return None

    # ------------------------------------------------------------------
    # Voice-service helpers
    # ------------------------------------------------------------------

    async def voice_announce(self, voice_payload: dict) -> dict | None:
        """POST to voice-service /api/voice/announce_with_completion."""
        url = f"{self.voice_url}/api/voice/announce_with_completion"
        try:
            async with self.session.post(
                url,
                json=voice_payload,
                headers=brain_auth_headers(),
                timeout=30,
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.warning(f"Voice generation failed: {e}")
        return None

    async def voice_synthesize(self, text: str, tone: str) -> dict | None:
        """POST to voice-service /api/voice/synthesize; returns response dict or None."""
        url = f"{self.voice_url}/api/voice/synthesize"
        try:
            async with self.session.post(
                url,
                json={"text": text, "tone": tone},
                headers=brain_auth_headers(),
                timeout=15,
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"Voice synthesize error: {e}")
        return None
