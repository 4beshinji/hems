#!/usr/bin/env python3
"""
Unit tests for duplicate task prevention and temperature alert improvements.

Tests the following fixes:
  1. tool_executor.py  — is_completed field + zone/type display
  2. dashboard_client.py — filter uses is_completed, location uses zone
  3. main.py — active tasks injected into LLM context
  4. tasks.py (backend) — zone+task_type duplicate check
  5. world_model.py — alert section in get_llm_context()

Usage:
  python3 infra/tests/integration/test_dedup_and_alerts.py          # unit tests only
  python3 infra/tests/integration/test_dedup_and_alerts.py --live    # + backend integration
"""
import sys
import os
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Add brain src to path for imports
BRAIN_SRC = os.path.join(os.path.dirname(__file__), "../../services/brain/src")
sys.path.insert(0, BRAIN_SRC)


# ────────────────────────────────────────────────────────
# Test 1: tool_executor._handle_get_active_tasks
# ────────────────────────────────────────────────────────
class TestToolExecutorActiveTasks(unittest.TestCase):
    """Bug1: tool_executor used non-existent 'status' field."""

    def _make_executor(self, mock_tasks):
        from tool_executor import ToolExecutor
        dashboard = MagicMock()
        dashboard.get_active_tasks = AsyncMock(return_value=mock_tasks)
        executor = ToolExecutor(
            sanitizer=MagicMock(),
            mcp_bridge=MagicMock(),
            dashboard_client=dashboard,
            world_model=MagicMock(),
            task_queue=MagicMock(),
        )
        return executor

    def test_uses_is_completed_field(self):
        """Result text should show 対応中/完了 based on is_completed, not status."""
        tasks = [
            {"title": "換気してください", "is_completed": False, "zone": "main", "task_type": ["environment"]},
            {"title": "完了済みタスク", "is_completed": True, "zone": "kitchen", "task_type": ["supply"]},
        ]
        executor = self._make_executor(tasks)
        result = asyncio.run(executor._handle_get_active_tasks())

        self.assertTrue(result["success"])
        text = result["result"]
        # Should contain is_completed-derived status, not 'status: '
        self.assertIn("対応中", text)
        self.assertIn("完了", text)
        self.assertNotIn("status:", text)

    def test_includes_zone_and_type(self):
        """Result should show zone and task_type info."""
        tasks = [
            {"title": "CO2対策", "is_completed": False, "zone": "meeting_room_a", "task_type": ["environment"]},
        ]
        executor = self._make_executor(tasks)
        result = asyncio.run(executor._handle_get_active_tasks())

        text = result["result"]
        self.assertIn("meeting_room_a", text)
        self.assertIn("environment", text)

    def test_empty_tasks(self):
        """No tasks should return a success message."""
        executor = self._make_executor([])
        result = asyncio.run(executor._handle_get_active_tasks())
        self.assertTrue(result["success"])
        self.assertIn("ありません", result["result"])

    def test_missing_optional_fields(self):
        """Tasks with missing zone/task_type should not crash."""
        tasks = [
            {"title": "タスク1", "is_completed": False},
            {"title": "タスク2", "is_completed": False, "zone": "", "task_type": []},
        ]
        executor = self._make_executor(tasks)
        result = asyncio.run(executor._handle_get_active_tasks())
        self.assertTrue(result["success"])


# ────────────────────────────────────────────────────────
# Test 2: dashboard_client.get_active_tasks filter
# ────────────────────────────────────────────────────────
class TestDashboardClientFilter(unittest.TestCase):
    """Bug2: filter used 'status' which doesn't exist in Task schema."""

    def test_filters_by_is_completed(self):
        """get_active_tasks should filter using is_completed, not status."""
        from dashboard_client import DashboardClient

        mock_response_data = [
            {"id": 1, "title": "Active Task", "is_completed": False},
            {"id": 2, "title": "Done Task", "is_completed": True},
            {"id": 3, "title": "Also Active", "is_completed": False},
        ]

        client = DashboardClient()

        async def run():
            with patch("aiohttp.ClientSession") as MockSession:
                mock_resp = AsyncMock()
                mock_resp.status = 200
                mock_resp.json = AsyncMock(return_value=mock_response_data)
                mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
                mock_resp.__aexit__ = AsyncMock(return_value=False)

                mock_session = AsyncMock()
                mock_session.get = MagicMock(return_value=mock_resp)
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)

                MockSession.return_value = mock_session

                active = await client.get_active_tasks()
                return active

        active = asyncio.run(run())
        self.assertEqual(len(active), 2)
        titles = [t["title"] for t in active]
        self.assertIn("Active Task", titles)
        self.assertIn("Also Active", titles)
        self.assertNotIn("Done Task", titles)


# ────────────────────────────────────────────────────────
# Test 2b: dashboard_client.create_task location uses zone
# ────────────────────────────────────────────────────────
class TestDashboardClientLocation(unittest.TestCase):
    """Bug3: create_task always used 'Office' as location."""

    def test_location_uses_zone_when_provided(self):
        """When zone is specified, location should be zone, not 'Office'."""
        from dashboard_client import DashboardClient

        client = DashboardClient(enable_voice=False)
        captured_payload = {}

        async def run():
            with patch("aiohttp.ClientSession") as MockSession:
                mock_resp = AsyncMock()
                mock_resp.status = 200
                mock_resp.json = AsyncMock(return_value={"id": 99})
                mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
                mock_resp.__aexit__ = AsyncMock(return_value=False)

                mock_session = AsyncMock()

                def capture_post(url, json=None):
                    captured_payload.update(json or {})
                    return mock_resp

                mock_session.post = MagicMock(side_effect=capture_post)
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)

                MockSession.return_value = mock_session

                await client.create_task(
                    title="Test",
                    description="desc",
                    zone="meeting_room_a",
                    announce=False,
                )

        asyncio.run(run())
        self.assertEqual(captured_payload.get("location"), "meeting_room_a")

    def test_location_falls_back_to_office(self):
        """When zone is None, location should fall back to 'Office'."""
        from dashboard_client import DashboardClient

        client = DashboardClient(enable_voice=False)
        captured_payload = {}

        async def run():
            with patch("aiohttp.ClientSession") as MockSession:
                mock_resp = AsyncMock()
                mock_resp.status = 200
                mock_resp.json = AsyncMock(return_value={"id": 100})
                mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
                mock_resp.__aexit__ = AsyncMock(return_value=False)

                mock_session = AsyncMock()

                def capture_post(url, json=None):
                    captured_payload.update(json or {})
                    return mock_resp

                mock_session.post = MagicMock(side_effect=capture_post)
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)

                MockSession.return_value = mock_session

                await client.create_task(
                    title="Test",
                    description="desc",
                    zone=None,
                    announce=False,
                )

        asyncio.run(run())
        self.assertEqual(captured_payload.get("location"), "Office")


# ────────────────────────────────────────────────────────
# Test 5: world_model.get_llm_context alert section
# ────────────────────────────────────────────────────────
class TestWorldModelAlerts(unittest.TestCase):
    """Temperature/CO2/humidity anomalies should appear as alerts."""

    def _make_wm(self):
        from world_model import WorldModel
        return WorldModel()

    def test_high_temperature_alert(self):
        """Temperature > 26 should produce a high-temp alert."""
        wm = self._make_wm()
        wm.update_from_mqtt("office/main/sensor/env_01/temperature", {"value": 38.0})
        ctx = wm.get_llm_context()
        self.assertIn("アラート", ctx)
        self.assertIn("高温", ctx)
        self.assertIn("38.0", ctx)

    def test_low_temperature_alert(self):
        """Temperature < 18 should produce a low-temp alert."""
        wm = self._make_wm()
        wm.update_from_mqtt("office/main/sensor/env_01/temperature", {"value": 15.0})
        ctx = wm.get_llm_context()
        self.assertIn("アラート", ctx)
        self.assertIn("低温", ctx)

    def test_normal_temperature_no_alert(self):
        """Temperature 18-26 should NOT produce an alert."""
        wm = self._make_wm()
        wm.update_from_mqtt("office/main/sensor/env_01/temperature", {"value": 22.0})
        ctx = wm.get_llm_context()
        self.assertNotIn("アラート", ctx)

    def test_high_co2_alert(self):
        """CO2 > 1000 should produce alert."""
        wm = self._make_wm()
        wm.update_from_mqtt("office/main/sensor/co2_01/co2", {"value": 2000})
        ctx = wm.get_llm_context()
        self.assertIn("アラート", ctx)
        self.assertIn("CO2", ctx)

    def test_normal_co2_no_alert(self):
        """CO2 <= 1000 should NOT produce alert."""
        wm = self._make_wm()
        wm.update_from_mqtt("office/main/sensor/co2_01/co2", {"value": 800})
        ctx = wm.get_llm_context()
        self.assertNotIn("アラート", ctx)

    def test_high_humidity_alert(self):
        """Humidity > 70 should produce alert."""
        wm = self._make_wm()
        wm.update_from_mqtt("office/main/sensor/env_01/humidity", {"value": 85.0})
        ctx = wm.get_llm_context()
        self.assertIn("アラート", ctx)
        self.assertIn("高湿度", ctx)

    def test_low_humidity_alert(self):
        """Humidity < 30 should produce alert."""
        wm = self._make_wm()
        wm.update_from_mqtt("office/main/sensor/env_01/humidity", {"value": 20.0})
        ctx = wm.get_llm_context()
        self.assertIn("アラート", ctx)
        self.assertIn("低湿度", ctx)

    def test_normal_humidity_no_alert(self):
        """Humidity 30-70 should NOT produce alert."""
        wm = self._make_wm()
        wm.update_from_mqtt("office/main/sensor/env_01/humidity", {"value": 50.0})
        ctx = wm.get_llm_context()
        self.assertNotIn("アラート", ctx)

    def test_multiple_zone_alerts(self):
        """Alerts from multiple zones should all appear."""
        wm = self._make_wm()
        wm.update_from_mqtt("office/room_a/sensor/env_01/temperature", {"value": 38.0})
        wm.update_from_mqtt("office/room_b/sensor/co2_01/co2", {"value": 2000})
        ctx = wm.get_llm_context()
        self.assertIn("room_a", ctx)
        self.assertIn("room_b", ctx)
        self.assertIn("高温", ctx)
        self.assertIn("CO2", ctx)

    def test_alert_section_appears_before_zone_data(self):
        """Alert section should appear at the top of the context."""
        wm = self._make_wm()
        wm.update_from_mqtt("office/main/sensor/env_01/temperature", {"value": 38.0})
        ctx = wm.get_llm_context()
        alert_pos = ctx.find("アラート")
        zone_pos = ctx.find("### main")
        self.assertGreater(zone_pos, alert_pos,
                           "Alert section should appear before zone data")


# ────────────────────────────────────────────────────────
# Test 3: main.py — active task injection into user message
# ────────────────────────────────────────────────────────
class TestCognitiveCycleTaskInjection(unittest.TestCase):
    """Bug5: LLM context had no active task info, causing duplicate creation."""

    def test_active_tasks_injected_into_user_content(self):
        """cognitive_cycle should add active tasks section to user message."""
        # We'll import Brain and mock its dependencies
        from main import Brain

        brain = Brain.__new__(Brain)
        brain.task_queue = MagicMock()
        brain.task_queue.process_queue = AsyncMock()

        # Set up world model with some data
        from world_model import WorldModel
        brain.world_model = WorldModel()
        brain.world_model.update_from_mqtt(
            "office/main/sensor/env_01/temperature", {"value": 22.0}
        )

        # Mock dashboard to return active tasks
        brain.dashboard = MagicMock()
        brain.dashboard.get_active_tasks = AsyncMock(return_value=[
            {"title": "換気してください", "zone": "main", "task_type": ["environment"]},
            {"title": "コーヒー豆補充", "zone": "kitchen", "task_type": ["supply"]},
        ])

        # Mock LLM to capture the messages it receives
        captured_messages = []

        async def mock_chat(messages, tools):
            captured_messages.extend(messages)
            resp = MagicMock()
            resp.error = None
            resp.tool_calls = []
            resp.content = "問題ありません。"
            return resp

        brain.llm = MagicMock()
        brain.llm.chat = mock_chat

        brain.tool_executor = MagicMock()

        asyncio.run(brain.cognitive_cycle())

        # Find the user message
        user_msgs = [m for m in captured_messages if m.get("role") == "user"]
        self.assertTrue(len(user_msgs) > 0, "Should have a user message")

        user_content = user_msgs[0]["content"]
        self.assertIn("現在のアクティブタスク", user_content)
        self.assertIn("重複作成禁止", user_content)
        self.assertIn("換気してください", user_content)
        self.assertIn("コーヒー豆補充", user_content)
        self.assertIn("[main]", user_content)
        self.assertIn("[kitchen]", user_content)

    def test_no_active_tasks_shows_none(self):
        """When no active tasks, should show なし."""
        from main import Brain

        brain = Brain.__new__(Brain)
        brain.task_queue = MagicMock()
        brain.task_queue.process_queue = AsyncMock()

        from world_model import WorldModel
        brain.world_model = WorldModel()
        brain.world_model.update_from_mqtt(
            "office/main/sensor/env_01/temperature", {"value": 22.0}
        )

        brain.dashboard = MagicMock()
        brain.dashboard.get_active_tasks = AsyncMock(return_value=[])

        captured_messages = []

        async def mock_chat(messages, tools):
            captured_messages.extend(messages)
            resp = MagicMock()
            resp.error = None
            resp.tool_calls = []
            resp.content = "OK"
            return resp

        brain.llm = MagicMock()
        brain.llm.chat = mock_chat
        brain.tool_executor = MagicMock()

        asyncio.run(brain.cognitive_cycle())

        user_msgs = [m for m in captured_messages if m.get("role") == "user"]
        user_content = user_msgs[0]["content"]
        self.assertIn("現在のアクティブタスク", user_content)
        self.assertIn("なし", user_content)


# ────────────────────────────────────────────────────────
# Test 4 (live): backend duplicate check via API
# ────────────────────────────────────────────────────────
class TestBackendDuplicateCheck(unittest.TestCase):
    """Bug4: Backend only checked exact title match. Now also checks zone+task_type.
    Requires running backend (--live flag)."""

    API_URL = "http://localhost:8000"

    @classmethod
    def setUpClass(cls):
        """Skip if backend is not reachable."""
        import urllib.request
        try:
            urllib.request.urlopen(f"{cls.API_URL}/tasks/stats", timeout=3)
        except Exception:
            raise unittest.SkipTest("Backend not reachable — skipping live tests")

    def _create_task(self, title, zone, task_type, urgency=2):
        import urllib.request
        from datetime import datetime, timedelta, timezone
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        payload = json.dumps({
            "title": title,
            "description": "test",
            "bounty_gold": 500,
            "task_type": task_type,
            "location": zone or "Office",
            "urgency": urgency,
            "zone": zone,
            "expires_at": expires,
        }).encode()
        req = urllib.request.Request(
            f"{self.API_URL}/tasks/",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def _complete_task(self, task_id):
        import urllib.request
        req = urllib.request.Request(
            f"{self.API_URL}/tasks/{task_id}/complete",
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def test_exact_title_dedup(self):
        """Same title + location should update existing, not create new."""
        t1 = self._create_task("TestDedup_ExactTitle", "test_zone", ["environment"])
        t2 = self._create_task("TestDedup_ExactTitle", "test_zone", ["environment"])
        self.assertEqual(t1["id"], t2["id"], "Should return same task ID (dedup)")
        # Cleanup
        self._complete_task(t1["id"])

    def test_zone_task_type_dedup(self):
        """Different title but same zone+task_type should deduplicate."""
        t1 = self._create_task("換気をお願いします_v1", "dedup_zone", ["environment"])
        t2 = self._create_task("部屋の換気が必要です_v2", "dedup_zone", ["environment"])
        self.assertEqual(t1["id"], t2["id"],
                         "Same zone+task_type should deduplicate even with different titles")
        # Cleanup
        self._complete_task(t1["id"])

    def test_different_zone_no_dedup(self):
        """Same task_type but different zone should NOT deduplicate."""
        t1 = self._create_task("換気A", "zone_a_test", ["environment"])
        t2 = self._create_task("換気B", "zone_b_test", ["environment"])
        self.assertNotEqual(t1["id"], t2["id"],
                            "Different zones should create separate tasks")
        # Cleanup
        self._complete_task(t1["id"])
        self._complete_task(t2["id"])

    def test_different_type_no_dedup(self):
        """Same zone but different task_type should NOT deduplicate."""
        t1 = self._create_task("タスクX", "shared_zone_test", ["environment"])
        t2 = self._create_task("タスクY", "shared_zone_test", ["supply"])
        self.assertNotEqual(t1["id"], t2["id"],
                            "Different task_types should create separate tasks")
        # Cleanup
        self._complete_task(t1["id"])
        self._complete_task(t2["id"])

    def test_completed_task_not_dedup(self):
        """Completed task should not block new task creation."""
        t1 = self._create_task("CompletedTest", "comp_zone", ["environment"])
        self._complete_task(t1["id"])
        t2 = self._create_task("CompletedTest", "comp_zone", ["environment"])
        self.assertNotEqual(t1["id"], t2["id"],
                            "Completed task should not prevent new task")
        # Cleanup
        self._complete_task(t2["id"])


# ────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────
if __name__ == "__main__":
    live = "--live" in sys.argv
    if "--live" in sys.argv:
        sys.argv.remove("--live")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Always run unit tests
    suite.addTests(loader.loadTestsFromTestCase(TestToolExecutorActiveTasks))
    suite.addTests(loader.loadTestsFromTestCase(TestDashboardClientFilter))
    suite.addTests(loader.loadTestsFromTestCase(TestDashboardClientLocation))
    suite.addTests(loader.loadTestsFromTestCase(TestWorldModelAlerts))
    suite.addTests(loader.loadTestsFromTestCase(TestCognitiveCycleTaskInjection))

    if live:
        suite.addTests(loader.loadTestsFromTestCase(TestBackendDuplicateCheck))
    else:
        print("ℹ️  Live backend tests skipped (use --live to include)\n")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
