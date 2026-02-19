"""
Tests for DashboardClient.push_gas_snapshot.
"""
from unittest.mock import MagicMock

import pytest
from world_model.data_classes import (
    GASState, CalendarEvent, GoogleTask, GmailLabel, FreeSlot,
)


class TestPushGASSnapshot:

    def _make_client(self, mock_session):
        from dashboard_client import DashboardClient
        client = DashboardClient(session=mock_session)
        return client

    @pytest.mark.asyncio
    async def test_skips_when_not_connected(self, world_model, mock_session):
        client = self._make_client(mock_session)
        world_model.gas_state.bridge_connected = False
        await client.push_gas_snapshot(world_model)
        for call in mock_session.post.call_args_list:
            assert "/gas/snapshot" not in str(call)

    @pytest.mark.asyncio
    async def test_pushes_when_connected(self, world_model, mock_session):
        client = self._make_client(mock_session)
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.calendar_events = [
            CalendarEvent(id="e1", title="Meeting", start="2026-02-19T10:00:00Z",
                          end="2026-02-19T11:00:00Z"),
        ]

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_gas_snapshot(world_model)
        mock_session.post.assert_called_once()
        call_url = mock_session.post.call_args[0][0]
        assert "/gas/snapshot" in call_url

    @pytest.mark.asyncio
    async def test_payload_contains_all_sections(self, world_model, mock_session):
        client = self._make_client(mock_session)
        gs = world_model.gas_state
        gs.bridge_connected = True
        gs.calendar_events = [
            CalendarEvent(id="e1", title="Standup", start="2026-02-19T10:00:00Z",
                          end="2026-02-19T10:30:00Z", is_all_day=False, calendar_name="Work"),
        ]
        gs.tasks = [
            GoogleTask(id="t1", title="Buy milk", due="2026-02-19", status="needsAction",
                       list_name="Tasks", is_overdue=True),
            GoogleTask(id="t2", title="Read paper", due="2026-02-20", status="needsAction",
                       list_name="Tasks", is_overdue=False),
        ]
        gs.gmail_labels = {"INBOX": GmailLabel(name="INBOX", unread=8)}
        gs.free_slots = [
            FreeSlot(start="2026-02-19T14:00:00Z", end="2026-02-19T16:00:00Z", duration_minutes=120),
        ]
        gs.last_calendar_update = 1.0
        gs.last_tasks_update = 2.0
        gs.last_gmail_update = 3.0

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_gas_snapshot(world_model)
        call_kwargs = mock_session.post.call_args[1]
        payload = call_kwargs["json"]

        assert payload["bridge_connected"] is True
        assert len(payload["calendar_events"]) == 1
        assert payload["calendar_events"][0]["title"] == "Standup"
        assert len(payload["tasks_due"]) == 2  # Both non-completed tasks
        assert payload["overdue_count"] == 1
        assert payload["gmail_inbox_unread"] == 8
        assert len(payload["free_slots"]) == 1
        assert payload["free_slots"][0]["duration_minutes"] == 120

    @pytest.mark.asyncio
    async def test_completed_tasks_excluded(self, world_model, mock_session):
        client = self._make_client(mock_session)
        gs = world_model.gas_state
        gs.bridge_connected = True
        gs.tasks = [
            GoogleTask(id="t1", title="Done", status="completed", list_name="Tasks"),
            GoogleTask(id="t2", title="Active", status="needsAction", list_name="Tasks"),
        ]

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_gas_snapshot(world_model)
        payload = mock_session.post.call_args[1]["json"]
        assert len(payload["tasks_due"]) == 1
        assert payload["tasks_due"][0]["title"] == "Active"
