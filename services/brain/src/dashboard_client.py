"""
REST client for HEMS Dashboard Backend.
"""
import os
from loguru import logger

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
VOICE_SERVICE_URL = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")


class DashboardClient:
    def __init__(self, session=None):
        self.session = session
        self.backend_url = BACKEND_URL
        self.voice_url = VOICE_SERVICE_URL

    async def create_task(self, task_data: dict) -> dict | None:
        """Create a task on the dashboard backend."""
        # Generate voice announcement first
        voice_data = await self._generate_voice(task_data)

        payload = {
            "title": task_data.get("title", ""),
            "description": task_data.get("description", ""),
            "location": task_data.get("location", ""),
            "xp_reward": task_data.get("xp_reward", 100),
            "urgency": task_data.get("urgency", 2),
            "zone": task_data.get("zone", ""),
            "task_type": task_data.get("task_type", []),
            "estimated_duration": task_data.get("estimated_duration", 10),
        }

        if voice_data:
            payload["announcement_audio_url"] = voice_data.get("announcement_audio_url")
            payload["announcement_text"] = voice_data.get("announcement_text")
            payload["completion_audio_url"] = voice_data.get("completion_audio_url")
            payload["completion_text"] = voice_data.get("completion_text")

        try:
            async with self.session.post(
                f"{self.backend_url}/tasks/", json=payload, timeout=10
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    text = await resp.text()
                    logger.warning(f"Create task failed: {resp.status} {text[:200]}")
        except Exception as e:
            logger.error(f"Create task error: {e}")
        return None

    async def _generate_voice(self, task_data: dict) -> dict | None:
        """Request voice announcement + completion from voice service."""
        voice_payload = {
            "task": {
                "title": task_data.get("title", ""),
                "description": task_data.get("description", ""),
                "location": task_data.get("location", ""),
                "xp_reward": task_data.get("xp_reward", 100),
                "urgency": task_data.get("urgency", 2),
                "zone": task_data.get("zone", ""),
                "task_type": task_data.get("task_type", []),
                "estimated_duration": task_data.get("estimated_duration", 10),
            }
        }
        try:
            async with self.session.post(
                f"{self.voice_url}/api/voice/announce_with_completion",
                json=voice_payload, timeout=30
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "announcement_audio_url": data.get("announcement_audio_url"),
                        "announcement_text": data.get("announcement_text"),
                        "completion_audio_url": data.get("completion_audio_url"),
                        "completion_text": data.get("completion_text"),
                    }
        except Exception as e:
            logger.warning(f"Voice generation failed: {e}")
        return None

    async def speak(self, message: str, zone: str, tone: str = "neutral") -> dict | None:
        """Send speak command through voice service + record event."""
        try:
            # Synthesize speech
            async with self.session.post(
                f"{self.voice_url}/api/voice/synthesize",
                json={"text": message, "tone": tone},
                timeout=15,
            ) as resp:
                if resp.status != 200:
                    return None
                voice_data = await resp.json()

            # Record voice event
            await self.session.post(
                f"{self.backend_url}/voice-events/",
                json={
                    "message": message,
                    "audio_url": voice_data.get("audio_url", ""),
                    "zone": zone,
                    "tone": tone,
                },
                timeout=5,
            )
            return voice_data
        except Exception as e:
            logger.error(f"Speak error: {e}")
            return None

    async def get_active_tasks(self) -> list:
        """Get active (non-completed) tasks from backend."""
        try:
            async with self.session.get(
                f"{self.backend_url}/tasks/", timeout=5
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.warning(f"Get active tasks error: {e}")
        return []

    async def push_pc_snapshot(self, world_model) -> None:
        """Push current PC metrics to backend for frontend consumption."""
        pc = world_model.pc_state
        if pc.cpu.last_update == 0 and pc.memory.last_update == 0:
            return  # No PC data yet

        payload = {
            "cpu": {
                "usage_percent": pc.cpu.usage_percent,
                "core_count": pc.cpu.core_count,
                "temp_c": pc.cpu.temp_c,
            },
            "memory": {
                "used_gb": pc.memory.used_gb,
                "total_gb": pc.memory.total_gb,
                "percent": pc.memory.percent,
            },
            "gpu": {
                "usage_percent": pc.gpu.usage_percent,
                "vram_used_gb": pc.gpu.vram_used_gb,
                "vram_total_gb": pc.gpu.vram_total_gb,
                "temp_c": pc.gpu.temp_c,
            },
            "disk": [
                {"mount": p.mount, "used_gb": p.used_gb, "total_gb": p.total_gb, "percent": p.percent}
                for p in pc.disk.partitions
            ],
            "top_processes": [
                {"pid": p.pid, "name": p.name, "cpu_percent": p.cpu_percent, "mem_mb": p.mem_mb}
                for p in pc.top_processes[:10]
            ],
            "bridge_connected": pc.bridge_connected,
        }
        try:
            async with self.session.post(
                f"{self.backend_url}/pc/snapshot",
                json=payload, timeout=5,
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"PC snapshot push failed: {resp.status}")
        except Exception as e:
            logger.debug(f"PC snapshot push error: {e}")

    async def push_services_snapshot(self, world_model) -> None:
        """Push current service statuses to backend for frontend consumption."""
        ss = world_model.services_state
        if not ss.services:
            return

        payload = {}
        for name, svc in ss.services.items():
            payload[name] = {
                "name": svc.name,
                "available": svc.available,
                "unread_count": svc.unread_count,
                "summary": svc.summary,
                "last_check": svc.last_check,
                "error": svc.error,
            }
        try:
            async with self.session.post(
                f"{self.backend_url}/services/snapshot",
                json=payload, timeout=5,
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"Services snapshot push failed: {resp.status}")
        except Exception as e:
            logger.debug(f"Services snapshot push error: {e}")

    async def push_zone_snapshot(self, world_model) -> None:
        """Push current zone sensor data to backend for frontend consumption."""
        zones = []
        for zone_id, zone in world_model.zones.items():
            env = zone.environment
            zones.append({
                "zone_id": zone_id,
                "environment": {
                    "temperature": env.temperature,
                    "humidity": env.humidity,
                    "co2": env.co2,
                    "pressure": env.pressure,
                    "light": env.light,
                    "voc": env.voc,
                    "last_update": env.last_update,
                },
                "occupancy": {
                    "count": zone.occupancy.count if zone.occupancy else 0,
                    "last_update": zone.occupancy.last_update if zone.occupancy else None,
                },
                "events": [
                    {"type": e.event_type, "description": e.description,
                     "severity": e.severity, "timestamp": e.timestamp}
                    for e in zone.events[-5:]
                ],
            })
        if not zones:
            return
        try:
            async with self.session.post(
                f"{self.backend_url}/zones/snapshot",
                json={"zones": zones}, timeout=5,
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"Zone snapshot push failed: {resp.status}")
        except Exception as e:
            logger.debug(f"Zone snapshot push error: {e}")
