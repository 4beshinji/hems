"""
Tests for WorldModel GAS state integration (MQTT routing + LLM context).
"""
import pytest


class TestWorldModelGASRouting:
    """Test hems/gas/* MQTT topic routing into GASState."""

    def test_calendar_upcoming_update(self, world_model):
        world_model.update_from_mqtt("hems/gas/calendar/upcoming", {
            "events": [
                {
                    "id": "ev1", "title": "Team Standup",
                    "start": "2026-02-19T10:00:00+09:00",
                    "end": "2026-02-19T10:30:00+09:00",
                    "location": "", "isAllDay": False,
                    "calendarName": "Work",
                },
                {
                    "id": "ev2", "title": "Lunch",
                    "start": "2026-02-19T12:00:00+09:00",
                    "end": "2026-02-19T13:00:00+09:00",
                    "location": "Cafeteria", "isAllDay": False,
                    "calendarName": "Personal",
                },
            ],
            "hours": 24,
        })
        gs = world_model.gas_state
        assert len(gs.calendar_events) == 2
        assert gs.calendar_events[0].title == "Team Standup"
        assert gs.calendar_events[1].location == "Cafeteria"
        assert gs.last_calendar_update > 0
        assert gs.bridge_connected is True

    def test_calendar_all_day_event(self, world_model):
        world_model.update_from_mqtt("hems/gas/calendar/upcoming", {
            "events": [
                {
                    "id": "ev3", "title": "Holiday",
                    "start": "2026-02-20", "end": "2026-02-21",
                    "location": "", "isAllDay": True, "calendarName": "Personal",
                },
            ],
        })
        ev = world_model.gas_state.calendar_events[0]
        assert ev.is_all_day is True
        # start_ts may parse depending on Python version; just verify no crash

    def test_calendar_free_slots(self, world_model):
        world_model.update_from_mqtt("hems/gas/calendar/free_slots", {
            "slots": [
                {"start": "2026-02-19T14:00:00+09:00", "end": "2026-02-19T16:00:00+09:00", "duration_minutes": 120},
                {"start": "2026-02-19T17:00:00+09:00", "end": "2026-02-19T18:00:00+09:00", "duration_minutes": 60},
            ],
        })
        gs = world_model.gas_state
        assert len(gs.free_slots) == 2
        assert gs.free_slots[0].duration_minutes == 120

    def test_tasks_all_update(self, world_model):
        world_model.update_from_mqtt("hems/gas/tasks/all", {
            "taskLists": [
                {
                    "id": "list1", "title": "My Tasks",
                    "tasks": [
                        {"id": "t1", "title": "Buy milk", "notes": "", "due": "2026-02-19", "status": "needsAction"},
                        {"id": "t2", "title": "Read paper", "notes": "AI paper", "due": "", "status": "needsAction"},
                    ],
                },
            ],
        })
        gs = world_model.gas_state
        assert len(gs.tasks) == 2
        assert gs.tasks[0].title == "Buy milk"
        assert gs.tasks[0].list_name == "My Tasks"
        assert gs.last_tasks_update > 0
        assert gs.bridge_connected is True

    def test_tasks_due_today_with_overdue(self, world_model):
        world_model.update_from_mqtt("hems/gas/tasks/due_today", {
            "taskLists": [
                {
                    "id": "list1", "title": "My Tasks",
                    "tasks": [
                        {"id": "t1", "title": "Overdue task", "notes": "", "due": "2026-02-17",
                         "status": "needsAction", "is_overdue": True, "list_name": "My Tasks"},
                    ],
                },
            ],
        })
        gs = world_model.gas_state
        assert len(gs.tasks) == 1
        assert gs.tasks[0].is_overdue is True

    def test_gmail_summary(self, world_model):
        world_model.update_from_mqtt("hems/gas/gmail/summary", {
            "labels": {
                "INBOX": {"unread": 12, "total": None},
                "Updates": {"unread": 5, "total": None},
            },
        })
        gs = world_model.gas_state
        assert "INBOX" in gs.gmail_labels
        assert gs.gmail_labels["INBOX"].unread == 12
        assert gs.gmail_labels["Updates"].unread == 5
        assert gs.last_gmail_update > 0

    def test_gmail_recent(self, world_model):
        world_model.update_from_mqtt("hems/gas/gmail/recent", {
            "threads": [
                {"id": "th1", "subject": "Hello", "from": "a@b.com", "date": "2026-02-19T08:00:00Z"},
            ],
        })
        gs = world_model.gas_state
        assert len(gs.gmail_recent) == 1
        assert gs.gmail_recent[0]["subject"] == "Hello"

    def test_sheets_update(self, world_model):
        world_model.update_from_mqtt("hems/gas/sheets/budget", {
            "headers": ["metric", "value", "threshold"],
            "values": [["food", 15000, 20000]],
        })
        gs = world_model.gas_state
        assert "budget" in gs.sheets
        assert gs.sheets["budget"].headers == ["metric", "value", "threshold"]
        assert gs.sheets["budget"].name == "budget"
        assert gs.bridge_connected is True

    def test_drive_recent(self, world_model):
        world_model.update_from_mqtt("hems/gas/drive/recent", {
            "files": [
                {"name": "Notes.docx", "mimeType": "application/vnd.google-apps.document",
                 "modifiedTime": "2026-02-19T10:00:00Z", "url": "https://docs.google.com/d/xxx"},
            ],
        })
        gs = world_model.gas_state
        assert len(gs.drive_recent) == 1
        assert gs.drive_recent[0].name == "Notes.docx"

    def test_bridge_status(self, world_model):
        world_model.update_from_mqtt("hems/gas/bridge/status", {
            "connected": True, "last_updates": {}, "timestamp": 1.0,
        })
        assert world_model.gas_state.bridge_connected is True

    def test_bridge_disconnect(self, world_model):
        world_model.update_from_mqtt("hems/gas/bridge/status", {"connected": True})
        world_model.update_from_mqtt("hems/gas/bridge/status", {"connected": False})
        assert world_model.gas_state.bridge_connected is False

    def test_unknown_gas_topic_ignored(self, world_model):
        world_model.update_from_mqtt("hems/gas/unknown/foo", {"bar": 1})
        # Should not crash

    def test_empty_path_ignored(self, world_model):
        world_model.update_from_mqtt("hems/gas", {})
        # Should not crash (caught by len(parts) >= 3 check)

    def test_calendar_start_timestamp_parsed(self, world_model):
        world_model.update_from_mqtt("hems/gas/calendar/upcoming", {
            "events": [
                {
                    "id": "ev1", "title": "Test",
                    "start": "2026-02-19T10:00:00+09:00",
                    "end": "2026-02-19T11:00:00+09:00",
                    "isAllDay": False,
                },
            ],
        })
        ev = world_model.gas_state.calendar_events[0]
        assert ev.start_ts > 0
        assert ev.end_ts > ev.start_ts


class TestWorldModelGASContext:
    """Test that GAS data appears in LLM context."""

    def test_no_gas_in_context_when_no_data(self, world_model):
        # GAS section should not appear when bridge is not connected
        world_model.gas_state.bridge_connected = False
        ctx = world_model.get_llm_context()
        assert "Google" not in ctx

    def test_gas_in_context_when_connected(self, world_model):
        # Use future timestamps so events pass the "upcoming" filter
        import time
        future_start = time.time() + 3600
        future_end = future_start + 1800
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.calendar_events = [
            __import__("world_model.data_classes", fromlist=["CalendarEvent"]).CalendarEvent(
                id="e1", title="Standup", start="2099-02-19T10:00:00+09:00",
                end="2099-02-19T10:30:00+09:00", start_ts=future_start, end_ts=future_end,
            ),
        ]
        ctx = world_model.get_llm_context()
        assert "### Google連携" in ctx
        assert "Standup" in ctx

    def test_gas_context_shows_tasks(self, world_model):
        world_model.update_from_mqtt("hems/gas/tasks/due_today", {
            "taskLists": [{"id": "l1", "title": "Tasks", "tasks": [
                {"id": "t1", "title": "Task A", "due": "2026-02-19", "status": "needsAction", "is_overdue": True},
                {"id": "t2", "title": "Task B", "due": "2026-02-19", "status": "needsAction", "is_overdue": False},
            ]}],
        })
        ctx = world_model.get_llm_context()
        assert "タスク" in ctx
        assert "期限切れ" in ctx

    def test_gas_context_shows_gmail(self, world_model):
        world_model.update_from_mqtt("hems/gas/gmail/summary", {
            "labels": {"INBOX": {"unread": 8, "total": None}},
        })
        ctx = world_model.get_llm_context()
        assert "Gmail未読" in ctx
        assert "8" in ctx

    def test_gas_context_no_events_shows_none(self, world_model):
        world_model.update_from_mqtt("hems/gas/calendar/upcoming", {
            "events": [],
        })
        ctx = world_model.get_llm_context()
        assert "予定: なし" in ctx

    def test_gas_context_free_slots(self, world_model):
        world_model.update_from_mqtt("hems/gas/calendar/upcoming", {"events": []})
        world_model.update_from_mqtt("hems/gas/calendar/free_slots", {
            "slots": [
                {"start": "2026-02-19T14:00:00+09:00", "end": "2026-02-19T16:00:00+09:00", "duration_minutes": 120},
            ],
        })
        ctx = world_model.get_llm_context()
        assert "空き時間" in ctx
