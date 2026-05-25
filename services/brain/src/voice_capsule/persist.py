"""Persist a capsule manifest via backend's admin POST endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from brain_constants import backend_auth_headers

if TYPE_CHECKING:
    import aiohttp


async def push_manifest(
    *,
    session: aiohttp.ClientSession,
    backend_url: str,
    manifest: dict,
) -> bool:
    """POST ``manifest`` to ``<backend_url>/mobile/voice-capsule``.

    Returns True iff the backend accepts (201). Failures are logged but
    never raised — boot-load must continue even when the phone companion
    subsystem is offline.
    """
    url = f"{backend_url.rstrip('/')}/mobile/voice-capsule"
    try:
        async with session.post(url, json=manifest, headers=backend_auth_headers(), timeout=15) as resp:
            if resp.status == 201:
                return True
            text = await resp.text()
            logger.warning(
                "capsule persist failed: status={} body={}",
                resp.status,
                text[:200],
            )
    except Exception as exc:
        logger.warning("capsule persist error: {}", exc)
    return False
