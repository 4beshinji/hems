"""
REST client for HEMS Dashboard Backend.

Public API is unchanged — callers (brain_startup, brain_loops, tool handlers)
interact only with DashboardClient and are not aware of the internal split.

Internal structure (W3.6 refactor):
  dashboard_transport.py  — HTTP / aiohttp session wrappers + auth headers
  dashboard_mappers.py    — pure world_model → payload serialisation functions
  dashboard_client.py     — this file: facade that delegates to the two above
"""

from datetime import UTC, datetime, timedelta

from loguru import logger

from dashboard_mappers import (
    map_biometric_payload,
    map_device_heartbeat_payload,
    map_gas_payload,
    map_home_payload,
    map_home_timeseries_points,
    map_knowledge_payload,
    map_news_payload,
    map_pc_payload,
    map_perception_zones,
    map_services_payload,
    map_weather_payload,
    map_zone_rows,
    map_zone_timeseries_points,
)
from dashboard_transport import BACKEND_URL, VOICE_SERVICE_URL, DashboardTransport

# Re-export constants so any code that did ``from dashboard_client import BACKEND_URL``
# continues to work without modification.
__all__ = ["BACKEND_URL", "VOICE_SERVICE_URL", "DashboardClient"]


class DashboardClient:
    def __init__(self, session=None):
        self.session = session
        self.backend_url = BACKEND_URL
        self.voice_url = VOICE_SERVICE_URL
        self._transport = DashboardTransport(session, self.backend_url, self.voice_url)

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    async def create_task(self, task_data: dict) -> dict | None:
        """Create a task on the dashboard backend."""
        task_type = task_data.get("task_type", [])

        expires_in_minutes = task_data.get("expires_in_minutes")
        if expires_in_minutes is None:
            expires_in_minutes = 60 * 24
            if "environment" in task_type:
                expires_in_minutes = min(expires_in_minutes, 60)
            if "supply" in task_type:
                expires_in_minutes = 60 * 24 * 7
            if "urgent" in task_type:
                expires_in_minutes = min(expires_in_minutes, 30)

        expires_at = (datetime.now(UTC) + timedelta(minutes=expires_in_minutes)).isoformat()

        voice_data = await self._generate_voice(task_data)

        payload = {
            "title": task_data.get("title", ""),
            "description": task_data.get("description", ""),
            "location": task_data.get("location", ""),
            "urgency": task_data.get("urgency", 2),
            "zone": task_data.get("zone", ""),
            "task_type": task_type,
            "estimated_duration": task_data.get("estimated_duration", 10),
            "expires_at": expires_at,
        }

        if voice_data:
            payload["announcement_audio_url"] = voice_data.get("announcement_audio_url")
            payload["announcement_text"] = voice_data.get("announcement_text")
            payload["completion_audio_url"] = voice_data.get("completion_audio_url")
            payload["completion_text"] = voice_data.get("completion_text")

        return await self._transport.post_and_return_json("/tasks/", payload, timeout=10)

    async def _generate_voice(self, task_data: dict) -> dict | None:
        """Request voice announcement + completion from voice service."""
        voice_payload = {
            "task": {
                "title": task_data.get("title", ""),
                "description": task_data.get("description", ""),
                "location": task_data.get("location", ""),
                "urgency": task_data.get("urgency", 2),
                "zone": task_data.get("zone", ""),
                "task_type": task_data.get("task_type", []),
                "estimated_duration": task_data.get("estimated_duration", 10),
            }
        }
        raw = await self._transport.voice_announce(voice_payload)
        if raw is None:
            return None
        return {
            "announcement_audio_url": raw.get("announcement_audio_url"),
            "announcement_text": raw.get("announcement_text"),
            "completion_audio_url": raw.get("completion_audio_url"),
            "completion_text": raw.get("completion_text"),
        }

    async def speak(self, message: str, zone: str, tone: str = "neutral") -> dict | None:
        """Send speak command through voice service + record event."""
        voice_data = await self._transport.voice_synthesize(message, tone)
        if voice_data is None:
            return None

        # Record voice event (fire-and-forget; ignore response)
        from brain_constants import backend_auth_headers

        try:
            await self.session.post(
                f"{self.backend_url}/voice-events/",
                headers=backend_auth_headers(),
                json={
                    "message": message,
                    "audio_url": voice_data.get("audio_url", ""),
                    "zone": zone,
                    "tone": tone,
                },
                timeout=5,
            )
        except Exception as e:
            logger.error(f"Speak error: {e}")

        return voice_data

    async def get_active_tasks(self) -> list:
        """Get active (non-completed) tasks from backend."""
        result = await self._transport.get_json("/tasks/")
        return result if isinstance(result, list) else []

    async def get_task_stats(self) -> dict:
        """Fetch task statistics from backend."""
        result = await self._transport.get_json("/tasks/stats")
        return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------------
    # Domain snapshot pushes
    # ------------------------------------------------------------------

    async def push_pc_snapshot(self, world_model) -> None:
        """Push current PC metrics to backend for frontend consumption."""
        payload = map_pc_payload(world_model)
        if payload is None:
            return
        await self._transport.post_snapshot("/pc/snapshot", payload)

    async def push_services_snapshot(self, world_model) -> None:
        """Push current service statuses to backend for frontend consumption."""
        payload = map_services_payload(world_model)
        if payload is None:
            return
        await self._transport.post_snapshot("/services/snapshot", payload)

    async def push_knowledge_snapshot(self, world_model) -> None:
        """Push current knowledge base status to backend for frontend consumption."""
        payload = map_knowledge_payload(world_model)
        if payload is None:
            return
        await self._transport.post_snapshot("/knowledge/snapshot", payload)

    async def push_gas_snapshot(self, world_model) -> None:
        """Push current GAS state to backend for frontend consumption."""
        payload = map_gas_payload(world_model)
        if payload is None:
            return
        await self._transport.post_snapshot("/gas/snapshot", payload)

    async def push_biometric_snapshot(self, world_model) -> None:
        """Push current biometric state to backend for frontend consumption."""
        payload = map_biometric_payload(world_model)
        if payload is None:
            return
        await self._transport.post_snapshot("/biometric/snapshot", payload)

    async def push_perception_snapshot(self, world_model) -> None:
        """Push current perception (camera) state to backend for frontend consumption."""
        zones_data = map_perception_zones(world_model)
        if zones_data is None:
            return
        await self._transport.post_snapshot("/perception/snapshot", {"zones": zones_data})

    async def push_home_snapshot(self, world_model) -> None:
        """Push current home device state to backend for frontend consumption."""
        payload = map_home_payload(world_model)
        if payload is None:
            return

        ts_points = map_home_timeseries_points(world_model)
        if ts_points:
            await self._transport.post_snapshot("/timeseries/ingest", {"points": ts_points})

        await self._transport.post_snapshot("/home/snapshot", payload)

    async def push_news_snapshot(self, world_model) -> None:
        """Push current news state to backend for frontend consumption."""
        payload = map_news_payload(world_model)
        if payload is None:
            return
        await self._transport.post_snapshot("/news/snapshot", payload)

    async def push_weather_snapshot(self, world_model) -> None:
        """Push current weather state (current/forecast/alerts) to backend."""
        payload = map_weather_payload(world_model)
        if payload is None:
            return
        await self._transport.post_snapshot("/weather/snapshot", payload)

    async def push_zone_snapshot(self, world_model) -> None:
        """Push current zone sensor data to backend for frontend consumption."""
        zones = map_zone_rows(world_model)
        if not zones:
            return
        await self._transport.post_snapshot("/zones/snapshot", {"zones": zones})

        ts_points = map_zone_timeseries_points(zones)
        if ts_points:
            await self._transport.post_snapshot("/timeseries/ingest", {"points": ts_points})

    # ------------------------------------------------------------------
    # Device & bridge helpers
    # ------------------------------------------------------------------

    async def push_device_action(
        self,
        device_id: str,
        action: str,
        params: dict | None = None,
        source: str = "llm",
        success: bool = True,
    ) -> None:
        """Push a device control action to backend log for 24h timeline view."""
        await self._transport.post_snapshot_multi_status(
            "/device-actions/",
            {
                "device_id": device_id,
                "action": action,
                "params": params or {},
                "source": source,
                "success": success,
            },
            ok_statuses=(200, 201),
        )

    async def push_bridge_status_event(self, service: str, connected: bool, detail: str = "") -> None:
        """Push a bridge state transition to backend SLA log."""
        await self._transport.post_snapshot_multi_status(
            "/bridge-status/event",
            {
                "service": service,
                "state": "connected" if connected else "disconnected",
                "detail": detail or None,
            },
            ok_statuses=(200, 201),
        )

    async def push_device_heartbeat(self, observation) -> dict | None:
        """Auto-register or refresh a device in the backend Device Registry."""
        payload = map_device_heartbeat_payload(observation)
        return await self._transport.post_and_return_json("/devices/heartbeat", payload)

    async def fetch_all_devices(self) -> list[dict]:
        """Fetch full device list for LLM context injection."""
        result = await self._transport.get_json("/devices/", params={"enabled_only": "true"})
        return result if isinstance(result, list) else []

    async def push_brain_snapshot(self, power_mode_status: dict, last_cycle: dict | None = None) -> None:
        """Push brain power mode status + last ReAct cycle summary to backend."""
        payload = dict(power_mode_status)
        if last_cycle is not None:
            payload["last_cycle"] = last_cycle

        from brain_constants import backend_auth_headers

        try:
            async with self.session.post(
                f"{self.backend_url}/brain/snapshot",
                headers=backend_auth_headers(),
                json=payload,
                timeout=5,
            ) as resp:
                if resp.status not in (200, 204):
                    logger.debug("Brain snapshot push HTTP %d", resp.status)
        except Exception as e:
            logger.debug("Brain snapshot push error: %s", e)
