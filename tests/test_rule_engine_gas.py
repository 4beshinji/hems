"""
Tests for RuleEngine GAS rules.
"""
import time
import pytest
from world_model.data_classes import (
    GASState, CalendarEvent, FreeSlot, GoogleTask, GmailLabel,
    DriveFile, SheetData,
)


class TestRuleEngineGASRules:
    """Test GAS-specific rules in the rule engine."""

    def _make_engine(self):
        from rule_engine import RuleEngine
        engine = RuleEngine()
        engine._cooldowns = {}
        return engine

    def _ts(self, offset_sec: float) -> float:
        """Current time + offset in seconds."""
        return time.time() + offset_sec

    # --- Calendar rules ---

    def test_meeting_reminder_10min(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.calendar_events = [
            CalendarEvent(
                id="ev1", title="Team Standup",
                start="2026-02-19T10:00:00+09:00",
                start_ts=self._ts(300),  # 5 min from now
                end_ts=self._ts(1800),
            ),
        ]
        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "Standup" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "alert"

    def test_meeting_reminder_not_fired_when_far(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.calendar_events = [
            CalendarEvent(
                id="ev1", title="Meeting",
                start_ts=self._ts(3600),  # 60 min from now
                end_ts=self._ts(5400),
            ),
        ]
        actions = engine.evaluate(world_model)
        meeting_speaks = [a for a in actions if a["tool"] == "speak" and "Meeting" in a["args"]["message"]]
        assert len(meeting_speaks) == 0

    def test_meeting_reminder_skips_all_day(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.calendar_events = [
            CalendarEvent(
                id="ev1", title="Holiday", is_all_day=True,
                start_ts=self._ts(300), end_ts=self._ts(86400),
            ),
        ]
        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "Holiday" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_overlap_detection(self, world_model):
        engine = self._make_engine()
        now = time.time()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.calendar_events = [
            CalendarEvent(id="ev1", title="Meeting A", start_ts=now + 100, end_ts=now + 3700),
            CalendarEvent(id="ev2", title="Meeting B", start_ts=now + 3600, end_ts=now + 7200),
        ]
        actions = engine.evaluate(world_model)
        overlaps = [a for a in actions if a["tool"] == "speak" and "重複" in a["args"]["message"]]
        assert len(overlaps) == 1

    def test_no_overlap_when_sequential(self, world_model):
        engine = self._make_engine()
        now = time.time()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.calendar_events = [
            CalendarEvent(id="ev1", title="A", start_ts=now + 100, end_ts=now + 3600),
            CalendarEvent(id="ev2", title="B", start_ts=now + 3600, end_ts=now + 7200),
        ]
        actions = engine.evaluate(world_model)
        overlaps = [a for a in actions if a["tool"] == "speak" and "重複" in a["args"]["message"]]
        assert len(overlaps) == 0

    # --- Task rules ---

    def test_overdue_alert(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.tasks = [
            GoogleTask(id="t1", title="Expired task", is_overdue=True, status="needsAction"),
        ]
        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "期限切れ" in a["args"]["message"]]
        assert len(speaks) == 1

    def test_no_overdue_alert_when_none(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.tasks = [
            GoogleTask(id="t1", title="On time task", is_overdue=False, status="needsAction"),
        ]
        actions = engine.evaluate(world_model)
        overdue = [a for a in actions if a["tool"] == "speak" and "期限切れ" in a["args"]["message"]]
        assert len(overdue) == 0

    # --- Gmail rules ---

    def test_gmail_unread_alert_10(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.gmail_labels = {"INBOX": GmailLabel(name="INBOX", unread=12)}
        actions = engine.evaluate(world_model)
        gmail_speaks = [a for a in actions if a["tool"] == "speak" and "未読" in a["args"]["message"]]
        assert len(gmail_speaks) == 1

    def test_gmail_critical_20_creates_task(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.gmail_labels = {"INBOX": GmailLabel(name="INBOX", unread=25)}
        actions = engine.evaluate(world_model)
        tasks = [a for a in actions if a["tool"] == "create_task" and "メール" in a["args"]["title"]]
        assert len(tasks) == 1

    def test_gmail_no_alert_below_threshold(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.gmail_labels = {"INBOX": GmailLabel(name="INBOX", unread=5)}
        actions = engine.evaluate(world_model)
        gmail = [a for a in actions if "未読" in a["args"].get("message", "")]
        assert len(gmail) == 0

    # --- Drive rules ---

    def test_drive_document_update_notification(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.drive_recent = [
            DriveFile(
                name="Budget 2026",
                mime_type="application/vnd.google-apps.spreadsheet",
                modified_time="2026-02-19T10:00:00Z",
                url="https://docs.google.com/spreadsheets/d/xxx",
            ),
        ]
        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "Budget" in a["args"]["message"]]
        assert len(speaks) == 1
        assert "スプレッドシート" in speaks[0]["args"]["message"]

    def test_drive_non_doc_ignored(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.drive_recent = [
            DriveFile(name="photo.jpg", mime_type="image/jpeg", modified_time="2026-02-19T10:00:00Z"),
        ]
        actions = engine.evaluate(world_model)
        drives = [a for a in actions if a["tool"] == "speak" and "photo" in a["args"].get("message", "")]
        assert len(drives) == 0

    # --- Sheets rules ---

    def test_sheet_threshold_alert(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.sheets = {
            "budget": SheetData(
                name="budget",
                headers=["metric", "value", "threshold"],
                values=[["food", 25000, 20000]],
                last_update=1.0,
            ),
        }
        actions = engine.evaluate(world_model)
        alerts = [a for a in actions if a["tool"] == "speak" and "food" in a["args"]["message"]]
        assert len(alerts) == 1
        assert "閾値超過" in alerts[0]["args"]["message"]

    def test_sheet_below_threshold_no_alert(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.sheets = {
            "budget": SheetData(
                name="budget",
                headers=["metric", "value", "threshold"],
                values=[["food", 15000, 20000]],
                last_update=1.0,
            ),
        }
        actions = engine.evaluate(world_model)
        alerts = [a for a in actions if a["tool"] == "speak" and "閾値" in a["args"].get("message", "")]
        assert len(alerts) == 0

    def test_sheet_without_required_columns_ignored(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.sheets = {
            "notes": SheetData(
                name="notes", headers=["title", "content"],
                values=[["Hello", "World"]], last_update=1.0,
            ),
        }
        actions = engine.evaluate(world_model)
        alerts = [a for a in actions if "閾値" in a["args"].get("message", "")]
        assert len(alerts) == 0

    # --- Cooldown ---

    def test_gas_cooldown_prevents_duplicate(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = True
        world_model.gas_state.gmail_labels = {"INBOX": GmailLabel(name="INBOX", unread=15)}

        actions1 = engine.evaluate(world_model)
        actions2 = engine.evaluate(world_model)

        gmail1 = [a for a in actions1 if "未読" in a["args"].get("message", "")]
        gmail2 = [a for a in actions2 if "未読" in a["args"].get("message", "")]
        assert len(gmail1) == 1
        assert len(gmail2) == 0

    # --- No action when bridge disconnected ---

    def test_no_gas_rules_when_disconnected(self, world_model):
        engine = self._make_engine()
        world_model.gas_state.bridge_connected = False
        world_model.gas_state.gmail_labels = {"INBOX": GmailLabel(name="INBOX", unread=50)}
        actions = engine.evaluate(world_model)
        gas_actions = [a for a in actions if "未読" in a["args"].get("message", "")
                       or "メール" in a["args"].get("title", "")]
        assert len(gas_actions) == 0
