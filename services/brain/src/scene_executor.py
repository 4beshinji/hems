"""
Scene executor — runs a list of device actions with per-action delay_s.

Each action is dispatched through DeviceDispatcher (vendor-agnostic). Delays are
honored via asyncio.sleep; total execution may be long-running (e.g. a wake scene
spanning 5 minutes), so execute_scene() is fire-and-forget from the caller's
perspective (task) unless wait=True.
"""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


class SceneExecutor:
    """Sequential (delay-sorted) executor. Each action block runs in order of delay_s."""

    def __init__(self, device_dispatcher, dashboard_client=None):
        self.dispatcher = device_dispatcher
        self.dashboard = dashboard_client  # for /scenes/{id}/execute stat bump (future)

    async def fetch_scene_by_name(self, name: str) -> dict | None:
        """Fetch a scene by programmatic name via backend."""
        if self.dashboard is None:
            return None
        scenes = await self._fetch_all()
        for s in scenes:
            if s.get("name") == name and s.get("is_enabled", True):
                return s
        return None

    async def list_scenes(self) -> list[dict]:
        if self.dashboard is None:
            return []
        return await self._fetch_all()

    async def _fetch_all(self) -> list[dict]:
        import aiohttp
        import os
        backend_url = os.getenv("BACKEND_URL", "http://backend:8000")
        api_key = os.getenv("HEMS_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            async with aiohttp.ClientSession(headers=headers) as s:
                async with s.get(
                    f"{backend_url}/scenes/?enabled_only=true",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.debug(f"Scene fetch failed: {e}")
        return []

    async def execute(self, actions: list[dict[str, Any]]) -> dict:
        """Execute a list of actions in order of delay_s.

        Returns {"success": bool, "executed": int, "errors": [str, ...]}.
        """
        if not actions:
            return {"success": True, "executed": 0, "errors": []}

        sorted_actions = sorted(
            actions, key=lambda a: int(a.get("delay_s") or 0)
        )
        errors: list[str] = []
        executed = 0
        elapsed = 0

        for step in sorted_actions:
            delay = int(step.get("delay_s") or 0)
            if delay > elapsed:
                await asyncio.sleep(delay - elapsed)
                elapsed = delay

            device_id = step.get("device_id", "")
            action = step.get("action", "")
            params = step.get("params") or {}
            if not device_id or not action:
                errors.append(f"invalid step: {step}")
                continue

            result = await self.dispatcher.dispatch(device_id, action, params)
            if result.get("success"):
                executed += 1
            else:
                errors.append(f"{device_id} {action}: {result.get('error', 'unknown')}")

        return {"success": not errors, "executed": executed, "errors": errors}

    async def execute_by_name(self, name: str) -> dict:
        scene = await self.fetch_scene_by_name(name)
        if scene is None:
            return {"success": False, "executed": 0,
                    "errors": [f"Scene '{name}' not found or disabled"]}
        return await self.execute(scene.get("actions") or [])
