"""
Periodic task reminder service — re-announces tasks after 1 hour.
"""
import asyncio
import os
from loguru import logger

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
VOICE_SERVICE_URL = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")
REMINDER_INTERVAL = 300  # Check every 5 minutes
REMINDER_THRESHOLD = 3600  # Re-announce after 1 hour


class TaskReminder:
    def __init__(self, session=None):
        self.session = session

    async def run_periodic_check(self):
        while True:
            await asyncio.sleep(REMINDER_INTERVAL)
            try:
                await self._check_and_remind()
            except Exception as e:
                logger.error(f"TaskReminder error: {e}")

    async def _check_and_remind(self):
        try:
            async with self.session.get(f"{BACKEND_URL}/tasks/", timeout=5) as resp:
                if resp.status != 200:
                    return
                tasks = await resp.json()
        except Exception as e:
            logger.warning(f"Failed to fetch tasks: {e}")
            return

        import time
        from datetime import datetime, timezone

        now = time.time()

        for task in tasks:
            if task.get("is_completed") or task.get("is_queued"):
                continue

            # Check if task needs reminding
            dispatched = task.get("dispatched_at")
            last_reminded = task.get("last_reminded_at")

            if not dispatched:
                continue

            # Parse ISO timestamp
            try:
                if last_reminded:
                    ref_time = datetime.fromisoformat(last_reminded.replace("Z", "+00:00"))
                else:
                    ref_time = datetime.fromisoformat(dispatched.replace("Z", "+00:00"))
                elapsed = now - ref_time.timestamp()
            except (ValueError, TypeError):
                continue

            if elapsed < REMINDER_THRESHOLD:
                continue

            # Re-announce
            logger.info(f"Reminding task {task['id']}: {task['title']}")

            # Synthesize reminder
            try:
                async with self.session.post(
                    f"{VOICE_SERVICE_URL}/api/voice/synthesize",
                    json={"text": f"リマインド: {task['title']}をお願いします。", "tone": "neutral"},
                    timeout=15,
                ) as resp:
                    if resp.status == 200:
                        voice_data = await resp.json()
                        # Record as voice event
                        await self.session.post(
                            f"{BACKEND_URL}/voice-events/",
                            json={
                                "message": f"リマインド: {task['title']}",
                                "audio_url": voice_data.get("audio_url", ""),
                                "zone": task.get("zone", ""),
                                "tone": "neutral",
                            },
                            timeout=5,
                        )
            except Exception as e:
                logger.warning(f"Reminder voice failed for task {task['id']}: {e}")

            # Update reminded timestamp
            try:
                await self.session.put(
                    f"{BACKEND_URL}/tasks/{task['id']}/reminded",
                    timeout=5,
                )
            except Exception as e:
                logger.warning(f"Failed to update reminded: {e}")
