"""
Task queue manager — dispatches queued tasks based on priority.
Simplified from SOMS for single-user home use.
"""

import aiohttp
from loguru import logger

from brain_constants import backend_auth_headers

from .decision import should_dispatch
from .priority import QueuedTask


class TaskQueueManager:
    def __init__(self, world_model, dashboard_client):
        self.world_model = world_model
        self.dashboard = dashboard_client

    async def add_task(self, task_id: int, title: str, urgency: int = 2, zone: str = ""):
        """Logging-only stub — does NOT enqueue anything itself.

        The task is already persisted in the backend DB at creation time, and
        process_queue() reads the queue straight from the backend each cycle.
        This method keeps no in-memory queue; it only emits an observability
        log line. Kept (rather than removed) so the create_task tool handler has
        a stable hook if local queueing is reintroduced later.
        """
        logger.info(f"Task queued: #{task_id} '{title}' (urgency={urgency}, zone={zone})")

    async def process_queue(self):
        """Check queued tasks and dispatch the highest priority one."""
        if self.dashboard is None or self.dashboard.session is None:
            return
        try:
            # Fetch queued tasks from backend via the shared session
            async with self.dashboard.session.get(
                f"{self.dashboard.backend_url}/tasks/queue",
                headers=backend_auth_headers(),
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
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
                await self.dashboard.session.put(
                    f"{self.dashboard.backend_url}/tasks/{qt.task_id}/dispatch",
                    headers=backend_auth_headers(),
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                break  # One dispatch per cycle

        except Exception as e:
            logger.warning(f"Queue processing error: {e}")
