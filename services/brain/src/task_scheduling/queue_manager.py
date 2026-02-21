"""
Task queue manager — dispatches queued tasks based on priority.
Simplified from SOMS for single-user home use.
"""
from loguru import logger
from .priority import QueuedTask
from .decision import should_dispatch


class TaskQueueManager:
    def __init__(self, world_model, dashboard_client):
        self.world_model = world_model
        self.dashboard = dashboard_client

    async def add_task(self, task_id: int, title: str, urgency: int = 2, zone: str = ""):
        """Register a newly created task for queue processing.

        The task is already persisted in the backend DB; this logs the addition
        so the next process_queue() cycle picks it up.
        """
        logger.info(f"Task queued: #{task_id} '{title}' (urgency={urgency}, zone={zone})")

    async def process_queue(self):
        """Check queued tasks and dispatch the highest priority one."""
        try:
            # Fetch queued tasks from backend
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.dashboard.backend_url}/tasks/queue") as resp:
                    if resp.status != 200:
                        return
                    tasks = await resp.json()

            if not tasks:
                return

            # Score and sort
            queued = []
            for t in tasks:
                qt = QueuedTask(
                    task_id=t["id"],
                    title=t.get("title", ""),
                    urgency=t.get("urgency", 2),
                    zone=t.get("zone", ""),
                    xp_reward=t.get("xp_reward", 100),
                )
                queued.append((qt.compute_priority(), qt))

            queued.sort(key=lambda x: -x[0])

            # Dispatch top task if conditions are met
            for _score, qt in queued:
                task_dict = {"urgency": qt.urgency, "zone": qt.zone}
                if not should_dispatch(task_dict, self.world_model):
                    logger.debug(f"Skipping task {qt.task_id}: dispatch conditions not met")
                    continue
                logger.info(f"Dispatching task {qt.task_id}: {qt.title}")
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    await session.put(f"{self.dashboard.backend_url}/tasks/{qt.task_id}/dispatch")
                break  # One dispatch per cycle

        except Exception as e:
            logger.warning(f"Queue processing error: {e}")
