"""
Tests for GAS-related data classes.
"""
from world_model.data_classes import (
    CalendarEvent, FreeSlot, GoogleTask, GmailLabel,
    DriveFile, SheetData, GASState, Event,
)


class TestCalendarEvent:
    def test_defaults(self):
        ev = CalendarEvent()
        assert ev.id == ""
        assert ev.title == ""
        assert ev.start_ts == 0
        assert ev.is_all_day is False

    def test_custom_values(self):
        ev = CalendarEvent(
            id="abc123", title="Meeting", start="2026-02-19T10:00:00Z",
            end="2026-02-19T11:00:00Z", location="Room A",
            calendar_name="Work", is_all_day=False, start_ts=1771495200.0,
        )
        assert ev.title == "Meeting"
        assert ev.location == "Room A"
        assert ev.start_ts == 1771495200.0


class TestFreeSlot:
    def test_defaults(self):
        slot = FreeSlot()
        assert slot.duration_minutes == 0

    def test_custom_values(self):
        slot = FreeSlot(start="2026-02-19T12:00:00Z", end="2026-02-19T14:00:00Z", duration_minutes=120)
        assert slot.duration_minutes == 120


class TestGoogleTask:
    def test_defaults(self):
        t = GoogleTask()
        assert t.status == ""
        assert t.is_overdue is False

    def test_overdue_task(self):
        t = GoogleTask(title="Buy groceries", due="2026-02-18", status="needsAction", is_overdue=True)
        assert t.is_overdue is True
        assert t.title == "Buy groceries"


class TestGmailLabel:
    def test_defaults(self):
        label = GmailLabel()
        assert label.unread == 0

    def test_with_unread(self):
        label = GmailLabel(name="INBOX", unread=15, total=200)
        assert label.unread == 15


class TestDriveFile:
    def test_defaults(self):
        f = DriveFile()
        assert f.name == ""
        assert f.mime_type == ""

    def test_document(self):
        f = DriveFile(
            name="Budget 2026", mime_type="application/vnd.google-apps.spreadsheet",
            modified_time="2026-02-19T08:00:00Z", url="https://docs.google.com/spreadsheets/d/xxx",
        )
        assert "spreadsheet" in f.mime_type


class TestSheetData:
    def test_defaults(self):
        s = SheetData()
        assert s.values == []
        assert s.headers == []

    def test_with_data(self):
        s = SheetData(name="budget", headers=["item", "amount"], values=[["food", 5000]], last_update=1.0)
        assert len(s.values) == 1
        assert s.headers[0] == "item"


class TestGASState:
    def test_defaults(self):
        gs = GASState()
        assert gs.bridge_connected is False
        assert gs.calendar_events == []
        assert gs.tasks == []
        assert gs.gmail_labels == {}
        assert gs.sheets == {}
        assert gs.drive_recent == []
        assert gs.events == []

    def test_event_ring_buffer(self):
        gs = GASState(max_events=5)
        for i in range(10):
            gs.add_event(Event(event_type=f"ev_{i}", description=f"Event {i}"))
        assert len(gs.events) == 5
        assert gs.events[0].event_type == "ev_5"
        assert gs.events[-1].event_type == "ev_9"

    def test_independent_instances(self):
        gs1 = GASState()
        gs2 = GASState()
        gs1.add_event(Event(event_type="only_in_gs1"))
        assert len(gs2.events) == 0
        assert len(gs1.calendar_events) == 0  # lists are independent too
