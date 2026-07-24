from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_get_active_tasks_excludes_completed_tasks():
    from dashboard_client import DashboardClient

    client = DashboardClient(session=MagicMock())
    client._transport.get_json = AsyncMock(
        return_value=[
            {"id": 1, "title": "active", "is_completed": False},
            {"id": 2, "title": "completed", "is_completed": True},
        ]
    )

    assert await client.get_active_tasks() == [{"id": 1, "title": "active", "is_completed": False}]
    client._transport.get_json.assert_awaited_once_with("/tasks/")
