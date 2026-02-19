import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from loguru import logger
import os

class TaskReminder:
    """
    Service to remind users about uncompleted tasks by regenerating announcement audio.

    Design:
    - Checks for tasks older than REMINDER_INTERVAL that haven't been reminded recently
    - Regenerates full announcement audio (not "reminder" audio - users may not have heard the first one)
    - Uses existing /api/voice/announce endpoint for consistency
    - LLM naturally generates different variations each time
    """

    # Configuration
    REMINDER_INTERVAL = int(os.getenv("REMINDER_INTERVAL_MINUTES", "60"))  # Default: 1 hour
    REMINDER_COOLDOWN = int(os.getenv("REMINDER_COOLDOWN_MINUTES", "30"))  # Minimum time between reminders
    CHECK_INTERVAL = int(os.getenv("REMINDER_CHECK_INTERVAL_SECONDS", "300"))  # How often to check (5 min)

    def __init__(self, dashboard_api_url=None, voice_service_url=None, session: aiohttp.ClientSession = None):
        self.dashboard_api_url = dashboard_api_url or os.getenv("DASHBOARD_API_URL", "http://backend:8000")
        self.voice_service_url = voice_service_url or os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")
        self._session = session
        logger.info(f"TaskReminder initialized - interval: {self.REMINDER_INTERVAL}m, cooldown: {self.REMINDER_COOLDOWN}m")

    async def get_tasks_needing_reminder(self):
        """
        Fetch tasks that need reminders.

        Criteria:
        - Not completed
        - Created more than REMINDER_INTERVAL ago
        - Either never reminded, or last reminded more than REMINDER_COOLDOWN ago
        """
        try:
            async with self._session.get(f"{self.dashboard_api_url}/tasks/") as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch tasks: {resp.status}")
                    return []

                tasks = await resp.json()

                now = datetime.now(timezone.utc)
                reminder_threshold = now - timedelta(minutes=self.REMINDER_INTERVAL)
                cooldown_threshold = now - timedelta(minutes=self.REMINDER_COOLDOWN)

                tasks_to_remind = []

                for task in tasks:
                    # Skip completed tasks
                    if task.get('is_completed'):
                        continue

                    # Check if task is old enough
                    created_at = datetime.fromisoformat(task['created_at'].replace('Z', '+00:00'))
                    if created_at > reminder_threshold:
                        continue

                    # Check if we've reminded too recently
                    last_reminded = task.get('last_reminded_at')
                    if last_reminded:
                        last_reminded_dt = datetime.fromisoformat(last_reminded.replace('Z', '+00:00'))
                        if last_reminded_dt > cooldown_threshold:
                            continue

                    tasks_to_remind.append(task)

                if tasks_to_remind:
                    logger.info(f"Found {len(tasks_to_remind)} tasks needing reminders")

                return tasks_to_remind

        except Exception as e:
            logger.error(f"Error fetching tasks for reminders: {e}")
            return []

    async def generate_reminder_audio(self, task):
        """
        Generate new announcement audio for a task.

        Uses the same /api/voice/announce endpoint to generate a fresh announcement.
        Thanks to LLM's variety, this will naturally be different from the original.
        """
        try:
            payload = {
                "task": {
                    "title": task.get("title"),
                    "description": task.get("description"),
                    "location": task.get("location"),
                    "bounty_gold": task.get("bounty_gold", 0),
                    "urgency": task.get("urgency", 2),
                    "zone": task.get("zone")
                }
            }

            logger.info(f"Generating reminder audio for task: {task.get('title')}")

            async with self._session.post(
                f"{self.voice_service_url}/api/voice/announce",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.info(f"Reminder audio generated: {result.get('text_generated')}")
                    return result
                else:
                    logger.error(f"Failed to generate reminder audio: {resp.status}")
                    return None

        except Exception as e:
            logger.error(f"Error generating reminder audio: {e}")
            return None

    async def update_reminder_timestamp(self, task_id):
        """Update the last_reminded_at timestamp for a task."""
        try:
            async with self._session.put(
                f"{self.dashboard_api_url}/tasks/{task_id}/reminded"
            ) as resp:
                if resp.status == 200:
                    logger.debug(f"Updated reminder timestamp for task {task_id}")
                    return True
                else:
                    logger.warning(f"Failed to update reminder timestamp: {resp.status}")
                    return False

        except Exception as e:
            logger.error(f"Error updating reminder timestamp: {e}")
            return False

    async def remind_task(self, task):
        """
        Send reminder for a single task.

        Steps:
        1. Generate new announcement audio
        2. Update last_reminded_at timestamp
        3. (Audio playback would be handled by frontend/notification system)
        """
        task_id = task.get('id')
        task_title = task.get('title')

        logger.info(f"Sending reminder for task #{task_id}: {task_title}")

        # Generate new audio
        audio_result = await self.generate_reminder_audio(task)
        if not audio_result:
            logger.error(f"Failed to generate audio for task #{task_id}")
            return False

        # Update timestamp
        success = await self.update_reminder_timestamp(task_id)
        if not success:
            logger.warning(f"Audio generated but timestamp update failed for task #{task_id}")

        logger.info(f"Reminder sent for task #{task_id}: {task_title}")
        return True

    async def check_and_remind(self):
        """Main reminder check loop - call this periodically."""
        logger.debug("Checking for tasks needing reminders...")

        tasks = await self.get_tasks_needing_reminder()

        if not tasks:
            logger.debug("No tasks need reminders")
            return

        # Process reminders
        for task in tasks:
            await self.remind_task(task)
            # Small delay between reminders to avoid overwhelming the system
            await asyncio.sleep(2)

    async def run_periodic_check(self):
        """
        Run the reminder check in a loop.
        This should be started as a background task.
        """
        logger.info(f"Starting periodic reminder checks (every {self.CHECK_INTERVAL}s)")

        while True:
            try:
                await self.check_and_remind()
            except Exception as e:
                logger.error(f"Error in reminder check loop: {e}")

            # Wait before next check
            await asyncio.sleep(self.CHECK_INTERVAL)
