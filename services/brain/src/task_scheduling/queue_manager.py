"""
Task queue manager — dispatches queued tasks based on priority.
Simplified from SOMS for single-user home use.
"""
from loguru import logger
from .priority import QueuedTask


class TaskQueueManager:
    def __init__(self, world_model, dashboard_client):
        self.world_model = world_model
        self.dashboard = dashboard_client

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

            # Dispatch top task
            top = queued[0][1]
            logger.info(f"Dispatching task {top.task_id}: {top.title}")

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                await session.put(f"{self.dashboard.backend_url}/tasks/{top.task_id}/dispatch")

        except Exception as e:
            logger.warning(f"Queue processing error: {e}")
