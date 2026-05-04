"""
Real-pipeline tests for wiring-gap-06 Wave 1-4 features.

Strategy: minimal mocking — only at I/O boundaries (HTTP sessions, MQTT publish
recorder). All core logic exercised on real WorldModel / RuleEngine / ToolExecutor /
MotionRetriever / EventWriter so refactors that change attribute paths or flow are
caught.

Covered:
  Wave 1: weather_alert rule + EventAutomation action, biometric stale labels
  Wave 2: gmail_recent context, free_slots HH:MM, vlm_history context,
          meeting_prep / overdue escalation / anomaly re-evaluation / heavy_process,
          new tools (gas_query_free_slots, gas_query_sheet, list_note_tags,
          list_cameras, get_vlm_status, get_activity_history,
          get_recent_knowledge_changes)
  Wave 3: BiometricState.history deque, trend rules (fatigue_streak / sleep_decline /
          stress_hr_coupling), trend tools, cause_event_id schema, notes/knowledge
          changed context exposure
  Wave 4: shopping/purchased cycle learning, fatigue→schedule wake_offset,
          stress→VLM publish, MotionRetriever rejection penalty + ack_learner feedback
"""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Wave 1 — Weather alerts + biometric stale labels
# ---------------------------------------------------------------------------


class TestWeatherAlertRule:
    """Wave 1.1 — _evaluate_weather_rules generates speak + create_task."""

    def _engine(self):
        from rule_engine import RuleEngine

        return RuleEngine()

    def _set_alert(self, world_model, severity: str, title: str = "大雨警報"):
        from world_model.data_classes import WeatherAlert

        # Weather rules only run when home_devices.bridge_connected is True
        # (or device_cache is populated). Set the bridge flag to enable the path.
        world_model.home_devices.bridge_connected = True
        w = world_model.weather
        w.last_alerts_update = time.time()
        w.alerts = [WeatherAlert(title=title, severity=severity, area="東京", description="非常に強い雨")]

    def test_warning_triggers_speak_and_task(self, world_model):
        self._set_alert(world_model, "warning")
        actions = self._engine().evaluate(world_model)
        wa_speaks = [a for a in actions if a["tool"] == "speak" and "大雨警報" in a["args"]["message"]]
        wa_tasks = [
            a for a in actions if a["tool"] == "create_task" and "weather_alert" in (a["args"].get("task_type") or [])
        ]
        assert len(wa_speaks) == 1
        assert wa_speaks[0]["args"]["tone"] == "caring"
        assert "東京" in wa_speaks[0]["args"]["message"]
        assert len(wa_tasks) == 1
        assert wa_tasks[0]["args"]["urgency"] == 3

    def test_critical_uses_alert_tone_and_higher_urgency(self, world_model):
        self._set_alert(world_model, "critical", "大雨特別警報")
        actions = self._engine().evaluate(world_model)
        wa_speaks = [a for a in actions if a["tool"] == "speak" and "特別警報" in a["args"]["message"]]
        wa_tasks = [
            a for a in actions if a["tool"] == "create_task" and "weather_alert" in (a["args"].get("task_type") or [])
        ]
        assert wa_speaks[0]["args"]["tone"] == "alert"
        assert wa_tasks[0]["args"]["urgency"] == 4

    def test_minor_severity_does_not_trigger(self, world_model):
        self._set_alert(world_model, "minor")
        actions = self._engine().evaluate(world_model)
        wa = [a for a in actions if a["tool"] == "speak" and "警報" in a["args"]["message"]]
        assert wa == []

    def test_repeat_within_24h_suppressed_by_cooldown(self, world_model):
        engine = self._engine()
        self._set_alert(world_model, "warning", title="洪水警報")
        first = engine.evaluate(world_model)
        second = engine.evaluate(world_model)
        first_speaks = [a for a in first if a["tool"] == "speak" and "洪水警報" in a["args"]["message"]]
        second_speaks = [a for a in second if a["tool"] == "speak" and "洪水警報" in a["args"]["message"]]
        assert len(first_speaks) == 1
        assert len(second_speaks) == 0


class TestWeatherAlertEventAutomation:
    """Wave 1.2 — weather_alert_announce action speaks active severe alerts."""

    def test_announce_speaks_each_severe_alert(self, world_model):
        from event_automation import EventAutomation
        from world_model.data_classes import WeatherAlert

        world_model.weather.last_alerts_update = time.time()
        world_model.weather.alerts = [
            WeatherAlert(title="大雨警報", severity="warning", area="東京"),
            WeatherAlert(title="洪水警報", severity="severe", area="多摩"),
            WeatherAlert(title="風速注意", severity="minor"),  # filtered
        ]

        recorded: list[tuple[str, dict]] = []

        class StubExecutor:
            async def execute(self, name, args):
                recorded.append((name, args))
                return {"success": True}

        ea = EventAutomation(tool_executor=StubExecutor(), world_model=world_model)
        asyncio.run(ea._action_weather_alert_announce())

        speak_msgs = [args["message"] for n, args in recorded if n == "speak"]
        assert any("大雨警報" in m for m in speak_msgs)
        assert any("洪水警報" in m for m in speak_msgs)
        assert not any("風速注意" in m for m in speak_msgs)
        assert all(args["tone"] == "alert" for n, args in recorded if n == "speak")

    def test_announce_no_alerts_no_speak(self, world_model):
        from event_automation import EventAutomation

        recorded: list[tuple[str, dict]] = []

        class StubExecutor:
            async def execute(self, name, args):
                recorded.append((name, args))
                return {"success": True}

        ea = EventAutomation(tool_executor=StubExecutor(), world_model=world_model)
        asyncio.run(ea._action_weather_alert_announce())
        assert recorded == []


class TestBiometricStaleLabels:
    """Wave 1.6 — _get_user_context tags biometrics with live/N分前/stale."""

    def test_live_label_for_fresh_data(self, world_model):
        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.heart_rate.bpm = 75
        bio.heart_rate.zone = "rest"
        bio.heart_rate.last_update = time.time() - 30  # 30s ago
        ctx = world_model._get_user_context()
        assert "(live)" in ctx
        assert "75bpm" in ctx

    def test_minutes_label_for_aged_data(self, world_model):
        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.heart_rate.bpm = 80
        bio.heart_rate.zone = "rest"
        bio.heart_rate.last_update = time.time() - 1500  # 25 min ago
        ctx = world_model._get_user_context()
        assert "25分前" in ctx
        assert "(live)" not in ctx

    def test_stale_label_for_old_data(self, world_model):
        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.heart_rate.bpm = 70
        bio.heart_rate.zone = "rest"
        bio.heart_rate.last_update = time.time() - 7200  # 2h ago
        ctx = world_model._get_user_context()
        assert "stale: 2時間前" in ctx


# ---------------------------------------------------------------------------
# Wave 2 — Context expansion + new rules + new tools
# ---------------------------------------------------------------------------


class TestGmailRecentContext:
    """Wave 2.1 — _get_digital_context lists VIP threads first, max 5."""

    def test_vip_first_then_truncate(self, world_model, monkeypatch):
        # Reload module with VIP env so _VIP_GMAIL_SENDERS is non-empty.
        import importlib

        monkeypatch.setenv("HEMS_GMAIL_VIP_SENDERS", "boss@example.com,partner@example.org")
        import world_model.world_model as wm_mod

        importlib.reload(wm_mod)

        wm = wm_mod.WorldModel()
        gs = wm.gas_state
        gs.bridge_connected = True
        gs.gmail_recent = [
            {"from": "newsletter@news.com", "subject": "週次ニュース", "snippet": "..."},
            {"from": "boss@example.com", "subject": "至急: 明日の会議", "snippet": "..."},
            {"from": "spam@junk.com", "subject": "勝者です", "snippet": "..."},
            {"from": "partner@example.org", "subject": "資料確認", "snippet": "..."},
            {"from": "x1@x.com", "subject": "x1", "snippet": ""},
            {"from": "x2@x.com", "subject": "x2", "snippet": ""},
            {"from": "x3@x.com", "subject": "x3", "snippet": ""},
        ]
        ctx = wm._get_digital_context()
        # VIPs (boss, partner) appear before non-VIPs in section
        boss_idx = ctx.find("boss@example.com")
        partner_idx = ctx.find("partner@example.org")
        spam_idx = ctx.find("spam@junk.com")
        assert boss_idx >= 0 and partner_idx >= 0
        assert boss_idx < spam_idx if spam_idx >= 0 else True
        # VIP star marker present
        assert "★" in ctx
        # Truncated to top 5 — at least one of x2/x3 should be missing
        assert not (("x2@x.com" in ctx) and ("x3@x.com" in ctx))


class TestFreeSlotsContext:
    """Wave 2.2 — free_slots formatted as HH:MM-HH:MM."""

    def test_top_three_slots_formatted(self, world_model):
        from world_model.data_classes import FreeSlot

        gs = world_model.gas_state
        gs.bridge_connected = True
        gs.free_slots = [
            FreeSlot(start="2026-05-03T14:00:00+00:00", end="2026-05-03T16:30:00+00:00", duration_minutes=150),
            FreeSlot(start="2026-05-03T18:00:00+00:00", end="2026-05-03T19:30:00+00:00", duration_minutes=90),
            FreeSlot(start="2026-05-03T20:00:00+00:00", end="2026-05-03T21:00:00+00:00", duration_minutes=60),
            FreeSlot(start="2026-05-03T22:00:00+00:00", end="2026-05-03T23:00:00+00:00", duration_minutes=60),
            FreeSlot(
                start="2026-05-03T11:00:00+00:00", end="2026-05-03T11:30:00+00:00", duration_minutes=30
            ),  # short — filtered
        ]
        ctx = world_model._get_digital_context()
        assert "14:00-16:30" in ctx
        assert "18:00-19:30" in ctx
        # Short slot must not appear
        assert "11:00-11:30" not in ctx


class TestVlmHistoryContext:
    """Wave 2.3 — _get_physical_context renders 1-line VLM history summary."""

    def test_history_line_appears_with_two_or_more_snapshots(self, world_model):
        from world_model.data_classes import SceneSnapshot

        zone = world_model._get_zone("living_room")
        now = time.time()
        zone.occupancy.vlm_last_update = now - 100
        zone.occupancy.vlm_history = [
            SceneSnapshot(timestamp=now - 600, description="片付いたリビング", objects=["sofa", "table"], tier="light"),
            SceneSnapshot(timestamp=now - 300, description="カップが置いてある", objects=["sofa", "cup"], tier="light"),
        ]
        ctx = world_model._get_physical_context()
        assert "VLM履歴" in ctx
        assert "sofa" in ctx
        assert "cup" in ctx

    def test_single_snapshot_no_history_line(self, world_model):
        from world_model.data_classes import SceneSnapshot

        zone = world_model._get_zone("living_room")
        zone.occupancy.vlm_last_update = time.time()
        zone.occupancy.vlm_history = [
            SceneSnapshot(timestamp=time.time(), description="x", objects=[], tier="light"),
        ]
        ctx = world_model._get_physical_context()
        assert "VLM履歴" not in ctx


class TestMeetingPrepRule:
    """Wave 2.4 — gas calendar event 25-30 min ahead → speak + brightness 178."""

    def _engine(self):
        from rule_engine import RuleEngine

        return RuleEngine()

    def test_event_28min_ahead_triggers_speak(self, world_model):
        from world_model.data_classes import CalendarEvent

        world_model.gas_state.bridge_connected = True
        ev_start = time.time() + 28 * 60
        world_model.gas_state.calendar_events = [
            CalendarEvent(
                id="meet1",
                title="設計レビュー",
                start_ts=ev_start,
                end_ts=ev_start + 3600,
                location="Room A",
            )
        ]
        actions = self._engine().evaluate(world_model)
        prep = [a for a in actions if a["tool"] == "speak" and "設計レビュー" in a["args"]["message"]]
        assert len(prep) == 1
        assert "30分後" in prep[0]["args"]["message"]
        assert "Room A" in prep[0]["args"]["message"]

    def test_event_5min_ahead_does_not_trigger(self, world_model):
        from world_model.data_classes import CalendarEvent

        world_model.gas_state.bridge_connected = True
        ev_start = time.time() + 5 * 60  # outside 25-30 window
        world_model.gas_state.calendar_events = [
            CalendarEvent(id="meet2", title="x", start_ts=ev_start, end_ts=ev_start + 3600)
        ]
        actions = self._engine().evaluate(world_model)
        prep = [a for a in actions if a["tool"] == "speak" and "30分後" in a["args"]["message"]]
        assert prep == []


class TestOverdueEscalation:
    """Wave 2.5 — overdue tasks escalate via stage A (initial) / B (24h) / C (72h)."""

    def _engine(self):
        from rule_engine import RuleEngine

        return RuleEngine()

    def _setup_overdue_task(self, world_model, hours_overdue: float):
        from world_model.data_classes import GoogleTask

        world_model.gas_state.bridge_connected = True
        due_dt = datetime.now(UTC) - timedelta(hours=hours_overdue)
        world_model.gas_state.tasks = [
            GoogleTask(
                id="t1",
                title="提案書作成",
                due=due_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                status="open",
                is_overdue=True,
            )
        ]

    def test_stage_b_24h_creates_priority_task(self, world_model):
        self._setup_overdue_task(world_model, hours_overdue=30)
        actions = self._engine().evaluate(world_model)
        b_tasks = [
            a
            for a in actions
            if a["tool"] == "create_task" and "overdue_escalation" in (a["args"].get("task_type") or [])
        ]
        assert any("【優先】" in a["args"]["title"] for a in b_tasks)

    def test_stage_c_72h_suggests_deletion(self, world_model):
        self._setup_overdue_task(world_model, hours_overdue=80)
        actions = self._engine().evaluate(world_model)
        c_tasks = [a for a in actions if a["tool"] == "create_task" and "削除候補" in a["args"].get("title", "")]
        assert len(c_tasks) == 1
        assert c_tasks[0]["args"]["urgency"] == 2

    def test_under_24h_no_escalation_task(self, world_model):
        self._setup_overdue_task(world_model, hours_overdue=12)
        actions = self._engine().evaluate(world_model)
        b_tasks = [
            a
            for a in actions
            if a["tool"] == "create_task" and "overdue_escalation" in (a["args"].get("task_type") or [])
        ]
        assert b_tasks == []


class TestAnomalyReevaluation:
    """Wave 2.6 — VLM anomaly persistence triggers escalate + 30min vlm/request."""

    def _engine_with_recorder(self):
        from rule_engine import RuleEngine

        published: list[tuple[str, dict]] = []

        def recorder(topic, payload):
            published.append((topic, payload))

        return RuleEngine(mqtt_publisher=recorder), published

    def _setup_anomaly(self, world_model, first_seen_offset: float):
        zone = world_model._get_zone("living_room")
        now = time.time()
        zone.occupancy.scene_anomalies = ["人が倒れている"]
        zone.occupancy.vlm_last_update = now - 30
        zone.occupancy.anomaly_first_seen = now - first_seen_offset
        zone.occupancy.anomaly_escalated = False
        zone.occupancy.anomaly_rescan_requested = 0

    def test_5min_persistence_escalates_with_task(self, world_model):
        engine, _ = self._engine_with_recorder()
        self._setup_anomaly(world_model, first_seen_offset=350)  # 5min50s
        actions = engine.evaluate(world_model)
        escalate_speaks = [a for a in actions if a["tool"] == "speak" and "5分経過" in a["args"]["message"]]
        escalate_tasks = [
            a for a in actions if a["tool"] == "create_task" and "vlm_anomaly" in (a["args"].get("task_type") or [])
        ]
        assert len(escalate_speaks) == 1
        assert len(escalate_tasks) == 1

    def test_30min_persistence_publishes_vlm_request(self, world_model):
        engine, published = self._engine_with_recorder()
        self._setup_anomaly(world_model, first_seen_offset=2000)  # >30min
        engine.evaluate(world_model)
        vlm_reqs = [(t, p) for t, p in published if t == "hems/perception/vlm/request"]
        assert len(vlm_reqs) == 1
        assert vlm_reqs[0][1]["reason"] == "anomaly_persisted_30min"


class TestHeavyProcessRule:
    """Wave 2.7 — sustained CPU >90% (5min) or process mem >4GB triggers speak."""

    def _engine(self):
        from rule_engine import RuleEngine

        return RuleEngine()

    def test_high_mem_single_process_triggers_speak(self, world_model):
        from world_model.data_classes import ProcessInfo

        pc = world_model.pc_state
        pc.bridge_connected = True
        pc.top_processes = [ProcessInfo(pid=1, name="custom_renderer", cpu_percent=10, mem_mb=4500)]
        actions = self._engine().evaluate(world_model)
        speaks = [
            a
            for a in actions
            if a["tool"] == "speak" and "custom_renderer" in a["args"]["message"] and "メモリ" in a["args"]["message"]
        ]
        assert len(speaks) == 1

    def test_excluded_chrome_does_not_alert_on_high_cpu(self, world_model, monkeypatch):
        from world_model.data_classes import ProcessInfo

        # PC_PROC_HEAVY_EXCLUDE is read at module-import time; monkeypatch + reload.
        monkeypatch.setenv("HEMS_PROC_HEAVY_EXCLUDE", "chrome,slack,code")
        import importlib

        import rule_engine as re_mod

        importlib.reload(re_mod)

        engine = re_mod.RuleEngine()
        pc = world_model.pc_state
        pc.bridge_connected = True
        # Inject a chrome process at high CPU. Even after sustaining, should be excluded.
        pc.top_processes = [ProcessInfo(pid=2, name="chrome.exe", cpu_percent=95, mem_mb=4500)]
        engine._heavy_proc_since["chrome.exe"] = time.time() - 600  # 10 min ago — sustained
        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "chrome" in a["args"]["message"].lower()]
        assert speaks == []

    def test_short_burst_does_not_trigger(self, world_model):
        from world_model.data_classes import ProcessInfo

        pc = world_model.pc_state
        pc.bridge_connected = True
        # First seen now → no sustain yet
        pc.top_processes = [ProcessInfo(pid=3, name="custom_app", cpu_percent=95, mem_mb=500)]
        engine = self._engine()
        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "custom_app" in a["args"]["message"]]
        assert speaks == []


class TestNewToolsExecutor:
    """Wave 2.8 / 2.9 — new tools dispatched correctly via ToolExecutor."""

    @pytest.mark.asyncio
    async def test_gas_query_free_slots_returns_ranges(self, tool_executor, world_model):
        from world_model.data_classes import FreeSlot

        future_start = (datetime.now(UTC) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        future_end = (datetime.now(UTC) + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        world_model.gas_state.free_slots = [
            FreeSlot(start=future_start, end=future_end, duration_minutes=120),
        ]
        result = await tool_executor.execute("gas_query_free_slots", {})
        assert result["success"]
        payload = json.loads(result["result"])
        assert payload["total"] == 1
        assert ":" in payload["slots"][0]["range"]
        assert payload["slots"][0]["duration_minutes"] == 120

    @pytest.mark.asyncio
    async def test_gas_query_sheet_returns_rows(self, tool_executor, world_model):
        from world_model.data_classes import SheetData

        world_model.gas_state.sheets["expenses"] = SheetData(
            name="expenses",
            headers=["date", "item", "amount"],
            values=[["2026-05-01", "coffee", 500], ["2026-05-02", "lunch", 1000]],
            last_update=time.time(),
        )
        result = await tool_executor.execute("gas_query_sheet", {"name": "expenses"})
        assert result["success"]
        payload = json.loads(result["result"])
        assert payload["found"]
        assert payload["row_count"] == 2
        assert payload["headers"] == ["date", "item", "amount"]

    @pytest.mark.asyncio
    async def test_gas_query_sheet_unknown_returns_available(self, tool_executor, world_model):
        from world_model.data_classes import SheetData

        world_model.gas_state.sheets["budget"] = SheetData(name="budget")
        result = await tool_executor.execute("gas_query_sheet", {"name": "missing"})
        payload = json.loads(result["result"])
        assert not payload["found"]
        assert "budget" in payload["available_sheets"]

    @pytest.mark.asyncio
    async def test_list_note_tags_calls_obsidian_endpoint(self, tool_executor, mock_session):
        tool_executor.obsidian_url = "http://obsidian-bridge:8000"
        resp = mock_session._make_response(200, {"tags": ["work", "ideas"], "total": 2})
        mock_session.get = MagicMock(return_value=resp)
        result = await tool_executor.execute("list_note_tags", {})
        assert result["success"]
        called_url = mock_session.get.call_args[0][0]
        assert called_url.endswith("/api/notes/tags")
        assert "work" in result["result"]

    @pytest.mark.asyncio
    async def test_list_cameras_requires_perception_url(self, tool_executor):
        tool_executor.perception_url = ""
        result = await tool_executor.execute("list_cameras", {})
        assert not result["success"]
        assert "Perception" in result["error"]

    @pytest.mark.asyncio
    async def test_get_activity_history_uses_world_model(self, tool_executor, world_model):
        from world_model.data_classes import SceneSnapshot

        zone = world_model._get_zone("living_room")
        zone.occupancy.activity_level = 0.42
        zone.occupancy.posture = "sitting"
        zone.occupancy.vlm_history = [
            SceneSnapshot(
                timestamp=time.time() - 120,
                description="reading book",
                objects=["book", "lamp"],
                tier="light",
                anomalies=[],
                scene_type="leisure",
            ),
        ]
        result = await tool_executor.execute("get_activity_history", {"zone_id": "living_room"})
        assert result["success"]
        payload = json.loads(result["result"])
        assert payload["zone"] == "living_room"
        assert payload["current_posture"] == "sitting"
        assert len(payload["snapshots"]) == 1
        assert payload["snapshots"][0]["description"] == "reading book"

    @pytest.mark.asyncio
    async def test_get_recent_knowledge_changes_calls_endpoint(self, tool_executor, mock_session):
        tool_executor.knowledge_url = "http://knowledge-bridge:8000"
        resp = mock_session._make_response(200, {"changes": [{"path": "a.md"}]})
        mock_session.get = MagicMock(return_value=resp)
        result = await tool_executor.execute("get_recent_knowledge_changes", {"limit": 5})
        assert result["success"]
        called_url = mock_session.get.call_args[0][0]
        assert called_url.endswith("/api/knowledge/recent")


# ---------------------------------------------------------------------------
# Wave 3 — Trend rules + tools + cause_event_id + notes/knowledge utilizer
# ---------------------------------------------------------------------------


class TestBiometricHistory:
    """Wave 3.1 — record_history appends to bounded deque."""

    def test_record_history_respects_maxlen(self, world_model):
        bio = world_model.biometric_state
        # heart_rate maxlen is 1440 — overflow test with smaller field
        sleep_q = bio.history["sleep_quality"]
        for i in range(20):
            bio.record_history("sleep_quality", float(i))
        assert len(sleep_q) == 14  # maxlen
        # Newest values retained
        values = [v for _, v in sleep_q]
        assert values[-1] == 19.0
        assert values[0] == 6.0

    def test_record_history_unknown_metric_silent(self, world_model):
        bio = world_model.biometric_state
        # Should not raise — no-op for unknown metric
        bio.record_history("nope_metric", 42)


class TestTrendRules:
    """Wave 3.2 — fatigue_streak / sleep_decline / stress_hr_coupling."""

    def _engine(self):
        from rule_engine import RuleEngine

        return RuleEngine()

    def test_fatigue_streak_3_days_high(self, world_model):
        bio = world_model.biometric_state
        bio.bridge_connected = True
        # Inject 3 distinct calendar days each peak ≥ 70
        now = time.time()
        for day_offset in (0, 1, 2):
            ts = now - day_offset * 86400
            bio.record_history("fatigue", 75.0, ts=ts)
            bio.record_history("fatigue", 85.0, ts=ts + 60)  # peak per day
        actions = self._engine().evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "3日連続" in a["args"]["message"]]
        tasks = [
            a for a in actions if a["tool"] == "create_task" and "fatigue_streak" in (a["args"].get("task_type") or [])
        ]
        assert len(speaks) == 1
        assert len(tasks) == 1

    def test_fatigue_streak_one_low_day_does_not_trigger(self, world_model):
        bio = world_model.biometric_state
        bio.bridge_connected = True
        now = time.time()
        peaks = [80.0, 50.0, 80.0]  # middle day below threshold
        for day_offset, peak in enumerate(peaks):
            ts = now - day_offset * 86400
            bio.record_history("fatigue", peak, ts=ts)
        actions = self._engine().evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "3日連続" in a["args"]["message"]]
        assert speaks == []

    def test_sleep_decline_15pct_drop(self, world_model):
        bio = world_model.biometric_state
        bio.bridge_connected = True
        now = time.time()
        # 7 prior days at quality 80, then 7 recent days at quality 60 → 25% drop
        for i in range(7):
            ts = now - (14 - i) * 86400
            bio.record_history("sleep_quality", 80.0, ts=ts)
        for i in range(7):
            ts = now - (7 - i) * 86400
            bio.record_history("sleep_quality", 60.0, ts=ts)
        actions = self._engine().evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "睡眠の質" in a["args"]["message"]]
        assert len(speaks) == 1
        assert "%" in speaks[0]["args"]["message"]

    def test_sleep_decline_stable_no_alert(self, world_model):
        bio = world_model.biometric_state
        bio.bridge_connected = True
        now = time.time()
        for i in range(14):
            ts = now - (14 - i) * 86400
            bio.record_history("sleep_quality", 80.0, ts=ts)
        actions = self._engine().evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "睡眠の質" in a["args"]["message"]]
        assert speaks == []

    def test_stress_hr_coupling(self, world_model):
        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.heart_rate.resting_bpm = 60
        now = time.time()
        # 5 stress samples in last 15min averaging > 70
        for i in range(5):
            bio.record_history("stress", 80.0, ts=now - i * 60)
        # 5 HR samples averaging > 60 * 1.2 = 72
        for i in range(5):
            bio.record_history("heart_rate", 90.0, ts=now - i * 60)
        # Required for the rule path that gates on bio.last_update
        bio.stress.level = 80
        bio.stress.last_update = now
        actions = self._engine().evaluate(world_model)
        coupling = [a for a in actions if a["tool"] == "speak" and "ストレスと心拍" in a["args"]["message"]]
        assert len(coupling) == 1
        assert "深呼吸" in coupling[0]["args"]["message"]


class TestStressVlmRequest:
    """Wave 4.7 — stress spike publishes hems/perception/vlm/request."""

    def test_high_stress_publishes_vlm_request(self, world_model):
        from rule_engine import RuleEngine

        published: list[tuple[str, dict]] = []
        engine = RuleEngine(mqtt_publisher=lambda t, p: published.append((t, p)))

        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.stress.level = 90
        bio.stress.last_update = time.time()
        engine.evaluate(world_model)
        vlm_reqs = [(t, p) for t, p in published if t == "hems/perception/vlm/request"]
        assert len(vlm_reqs) == 1
        assert vlm_reqs[0][1]["reason"] == "stress_spike"


class TestTrendTools:
    """Wave 3.3 — get_biometric_trend / get_sleep_history return correct shapes."""

    @pytest.mark.asyncio
    async def test_get_biometric_trend_returns_samples_and_stats(self, tool_executor, world_model):
        bio = world_model.biometric_state
        now = time.time()
        for i in range(10):
            bio.record_history("heart_rate", 60 + i, ts=now - (10 - i) * 60)
        result = await tool_executor.execute("get_biometric_trend", {"metric": "heart_rate", "window_hours": 1})
        assert result["success"]
        payload = json.loads(result["result"])
        assert payload["count"] == 10
        assert payload["stats"]["min"] == 60
        assert payload["stats"]["max"] == 69

    @pytest.mark.asyncio
    async def test_get_biometric_trend_unknown_metric_empty(self, tool_executor):
        result = await tool_executor.execute("get_biometric_trend", {"metric": "garbage"})
        assert result["success"]
        payload = json.loads(result["result"])
        assert payload["count"] == 0

    @pytest.mark.asyncio
    async def test_get_sleep_history_pairs_quality_duration(self, tool_executor, world_model):
        bio = world_model.biometric_state
        now = time.time()
        for i in range(3):
            ts = now - (3 - i) * 86400
            bio.record_history("sleep_quality", 70 + i, ts=ts)
            bio.record_history("sleep_duration", 420 + i * 10, ts=ts)
        result = await tool_executor.execute("get_sleep_history", {"days": 7})
        payload = json.loads(result["result"])
        assert payload["session_count"] == 3
        assert payload["avg_quality"] is not None
        assert payload["avg_duration_minutes"] is not None


class TestCauseEventId:
    """Wave 3.10 — event_store writer accepts and stores cause_event_id."""

    @pytest.mark.asyncio
    async def test_record_decision_propagates_cause_event_id(self, tmp_path, monkeypatch):
        # Build a temp sqlite engine directly — avoids module reload state pollution
        # that happens when tests share the global _engine.
        import sys as _sys

        # Ensure event_store wasn't poisoned by an earlier test substituting it
        # with a MagicMock (test_vlm.py does this). If poisoned, drop and re-import.
        _es = _sys.modules.get("event_store")
        if _es is not None and not hasattr(_es, "__path__"):
            for k in list(_sys.modules.keys()):
                if k == "event_store" or k.startswith("event_store."):
                    del _sys.modules[k]

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        db_url = f"sqlite+aiosqlite:///{tmp_path / 'es.db'}"
        engine = create_async_engine(db_url)
        # Apply the same DDL as init_db() (sqlite branch)
        from event_store.database import DDL_SQLITE

        async with engine.begin() as conn:
            for stmt in DDL_SQLITE.split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.execute(text(stmt))

        from event_store.writer import EventWriter

        writer = EventWriter(engine)
        writer.record_decision(
            cycle_duration=1.5,
            iterations=2,
            total_tool_calls=3,
            cause_event_id=42,
        )
        await writer._flush()

        async with engine.begin() as conn:
            row = (
                await conn.execute(text("SELECT cause_event_id FROM llm_decisions ORDER BY id DESC LIMIT 1"))
            ).first()
        assert row is not None
        assert row[0] == 42
        await engine.dispose()


class TestKnowledgeChangedContext:
    """Wave 3.11 — _get_digital_context surfaces recent knowledge changes."""

    def test_recent_changes_appear_in_context(self, world_model):
        ks = world_model.knowledge_state
        ks.bridge_connected = True
        ks.total_notes = 12
        ks.add_recent_change({"path": "ideas/x.md", "title": "新案 A", "action": "modified"})
        ks.add_recent_change({"path": "log/y.md", "title": "log Y", "action": "created"})
        ctx = world_model._get_digital_context()
        assert "新案 A" in ctx or "log Y" in ctx


# ---------------------------------------------------------------------------
# Wave 4 — Shopping cycle / fatigue→schedule / HRV / MotionRetriever
# ---------------------------------------------------------------------------


class TestShoppingCycleLearning:
    """Wave 4.5 — handle_purchased_event learns recurrence_days from history."""

    @pytest.mark.asyncio
    async def test_three_purchases_seven_days_apart_learn_cycle(self, mock_session):
        from annotator.shopping_classifier import ShoppingClassifier

        # Backend returns 3 historical purchases 7 days apart
        now = datetime.now(UTC)
        history = [
            {"id": 1, "name": "コーヒー豆", "purchased_at": (now - timedelta(days=21)).strftime("%Y-%m-%dT%H:%M:%SZ")},
            {"id": 2, "name": "コーヒー豆", "purchased_at": (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")},
            {"id": 3, "name": "コーヒー豆", "purchased_at": (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        ]
        get_resp = mock_session._make_response(200, history)
        patch_resp = mock_session._make_response(200, {"updated": True})
        mock_session.get = MagicMock(return_value=get_resp)
        mock_session.patch = MagicMock(return_value=patch_resp)

        classifier = ShoppingClassifier(session=mock_session, backend_url="http://backend:8000")
        ok = await classifier.handle_purchased_event({"id": 4, "name": "コーヒー豆"})
        assert ok
        # PATCH body: recurrence_days ≈ 7
        patch_call = mock_session.patch.call_args
        body = patch_call[1]["json"]
        assert body["is_recurring"] is True
        assert body["recurrence_days"] == 7

    @pytest.mark.asyncio
    async def test_two_purchases_no_cycle_learned(self, mock_session):
        from annotator.shopping_classifier import ShoppingClassifier

        now = datetime.now(UTC)
        history = [
            {"id": 1, "name": "アイテム", "purchased_at": (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")},
            {"id": 2, "name": "アイテム", "purchased_at": (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        ]
        mock_session.get = MagicMock(return_value=mock_session._make_response(200, history))
        mock_session.patch = MagicMock(return_value=mock_session._make_response(200, {}))
        classifier = ShoppingClassifier(session=mock_session, backend_url="http://backend:8000")
        ok = await classifier.handle_purchased_event({"id": 3, "name": "アイテム"})
        assert not ok
        # PATCH should not have been called
        assert mock_session.patch.call_count == 0


class TestFatigueWakeOffset:
    """Wave 4.7 — fatigue ≥60 delays predicted wake (linear up to 30 min @ 100)."""

    @staticmethod
    def _seed_history(sl):
        # The fatigue offset is only applied on the historical-pattern branch
        # (not FALLBACK_WAKE_TIME). Seed both today's and tomorrow's weekday
        # with a wake hour ~4h ahead of now so the historical branch always
        # fires regardless of when the test runs, and ≤30min fatigue offset
        # never crosses midnight.
        now = datetime.now()
        safe_hour = (now.hour + 4) % 24 + (now.minute / 60.0)
        sl._wake_history[now.weekday()] = [safe_hour] * 4
        sl._wake_history[(now + timedelta(days=1)).weekday()] = [safe_hour] * 4

    def test_fatigue_70_delays_wake_by_450s(self):
        # min(70-60, 40) * 45 = 10 * 45 = 450
        from schedule_learner import ScheduleLearner

        sl = ScheduleLearner()
        self._seed_history(sl)

        no_fatigue = sl.get_wake_time(fatigue_score=None)
        with_fatigue = sl.get_wake_time(fatigue_score=70)
        assert no_fatigue is not None
        assert with_fatigue is not None
        assert with_fatigue - no_fatigue == 450  # 7.5 minutes

    def test_fatigue_below_60_no_offset(self):
        from schedule_learner import ScheduleLearner

        sl = ScheduleLearner()
        self._seed_history(sl)

        no_fatigue = sl.get_wake_time(fatigue_score=None)
        with_fatigue = sl.get_wake_time(fatigue_score=50)
        assert no_fatigue is not None
        assert with_fatigue is not None
        assert no_fatigue == with_fatigue


class TestHrvFatigueFormula:
    """Wave 4.8 — fatigue_score includes HRV component (15%)."""

    def test_low_hrv_increases_fatigue(self):
        # Resolve biometric-bridge data_processor; it lives outside conftest sys.path
        import importlib.util as _ilu
        import sys as _sys

        bridge_src = Path(__file__).resolve().parent.parent / "services" / "biometric-bridge" / "src"
        _sys.path.insert(0, str(bridge_src))
        try:
            spec = _ilu.spec_from_file_location("bb_data_processor", bridge_src / "data_processor.py")
            mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            _sys.path.remove(str(bridge_src))

        # Build a low-HRV reading vs high-HRV reading and compare.
        # _latest is the only state compute_fatigue() needs for HRV/stress paths.
        proc_low = mod.DataProcessor()
        proc_low._latest = mod.BiometricReading(heart_rate=70, hrv_ms=15, stress_level=20, provider="t")
        score_low = proc_low.compute_fatigue()["score"]

        proc_high = mod.DataProcessor()
        proc_high._latest = mod.BiometricReading(heart_rate=70, hrv_ms=80, stress_level=20, provider="t")
        score_high = proc_high.compute_fatigue()["score"]

        # Lower HRV should yield higher fatigue score
        assert score_low > score_high

    def test_hrv_in_factors_when_low(self):
        import importlib.util as _ilu
        import sys as _sys

        bridge_src = Path(__file__).resolve().parent.parent / "services" / "biometric-bridge" / "src"
        _sys.path.insert(0, str(bridge_src))
        try:
            spec = _ilu.spec_from_file_location("bb_data_processor", bridge_src / "data_processor.py")
            mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            _sys.path.remove(str(bridge_src))

        proc = mod.DataProcessor()
        proc._latest = mod.BiometricReading(hrv_ms=15, provider="t")
        result = proc.compute_fatigue()
        assert "very_low_hrv" in result["factors"]


class TestMotionRetrieverRejection:
    """Wave 4.9 — record_rejection adds penalty + ack_learner feeds rejections."""

    def _make_retriever_with_motion(self, motion_id: str = "wave_1"):
        from motion_retriever import MotionRetriever

        # Use a tmp empty config so init succeeds without yaml — then inject a motion.
        mr = MotionRetriever(config_path=Path("/nonexistent.yaml"))
        from motion_retriever import MotionEntry

        entry = MotionEntry(
            id=motion_id,
            file=f"{motion_id}.vrma",
            name="wave",
            description="hello wave",
            tags=["greet"],
            duration=2.0,
            category="gesture",
        )
        from motion_retriever import _tokenize

        entry.tokens = _tokenize("hello wave greet")
        mr.motions.append(entry)
        mr._usage[motion_id] = {"count": 0, "last_seq": 0, "rejections": 0}
        return mr, motion_id

    def test_rejection_increases_penalty_score(self):
        mr, mid = self._make_retriever_with_motion()
        assert mr._rejection_penalty(mid) == 0.0
        mr.record_rejection(mid)
        assert mr._rejection_penalty(mid) == pytest.approx(0.4)
        mr.record_rejection(mid)
        assert mr._rejection_penalty(mid) == pytest.approx(0.8)

    def test_penalty_decays_after_three_uses(self):
        mr, mid = self._make_retriever_with_motion()
        mr.record_rejection(mid)  # rejections=1, count_at_last_reject=0
        # Simulate 3 successful uses
        for _ in range(3):
            mr._record_usage(mid)
        assert mr._rejection_penalty(mid) == pytest.approx(0.2)  # 0.4 * 0.5

    def test_record_rejection_unknown_motion_silent(self):
        mr, _ = self._make_retriever_with_motion()
        mr.record_rejection("does_not_exist")  # should not raise

    @pytest.mark.asyncio
    async def test_ack_learner_feeds_motion_rejections(self, mock_session):
        """≥2 rejections in play-log → ack_learner calls record_rejection on retriever."""
        from voice_capsule.ack_learner import AckLearner

        mr_calls: list[str] = []

        class FakeRetriever:
            def record_rejection(self, motion_id):
                mr_calls.append(motion_id)

        # Play-log: 2 rejected entries (drift > 600s) for same motion_id
        play_log = [
            {"clip_id": "shop_x", "trigger_drift_sec": 800, "context_json": {"motion_id": "wave_1"}},
            {"clip_id": "shop_x", "trigger_drift_sec": 900, "context_json": {"motion_id": "wave_1"}},
        ]
        mock_session.get = MagicMock(
            side_effect=[
                mock_session._make_response(200, play_log),
                mock_session._make_response(200, []),  # _list_event_lead_entries
            ]
        )
        learner = AckLearner(
            session=mock_session,
            backend_url="http://backend:8000",
            motion_retriever=FakeRetriever(),
        )
        await learner.run(since_days=7)
        assert mr_calls == ["wave_1"]

    @pytest.mark.asyncio
    async def test_ack_learner_single_rejection_ignored(self, mock_session):
        from voice_capsule.ack_learner import AckLearner

        mr_calls: list[str] = []

        class FakeRetriever:
            def record_rejection(self, motion_id):
                mr_calls.append(motion_id)

        play_log = [
            {"clip_id": "shop_x", "trigger_drift_sec": 800, "context_json": {"motion_id": "wave_1"}},
            # second entry uses different motion or normal drift — only 1 rejection for wave_1
        ]
        mock_session.get = MagicMock(
            side_effect=[
                mock_session._make_response(200, play_log),
                mock_session._make_response(200, []),
            ]
        )
        learner = AckLearner(
            session=mock_session,
            backend_url="http://backend:8000",
            motion_retriever=FakeRetriever(),
        )
        await learner.run(since_days=7)
        assert mr_calls == []  # below threshold


# ---------------------------------------------------------------------------
# Bonus: smoke verify the unwired-now-wired dashboard cards' API helpers.
# ---------------------------------------------------------------------------


class TestBackendApisForRefactoredCards:
    """Sanity check: backend routers feeding 4.2-4.4 dashboard cards exist."""

    def test_bridge_status_router_registered(self):
        # backend main.py registers the routers — check class import succeeds
        from routers import bridge_status, device_actions, news, weather

        assert bridge_status.router is not None
        assert device_actions.router is not None
        assert weather.router is not None
        assert news.router is not None
