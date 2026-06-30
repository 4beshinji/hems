"""Tests for rollback planner / executor / watcher (Phase 0 HITL)."""

import pytest

from approval.rollback_executor import RollbackExecutor
from approval.rollback_planner import RollbackPlan, build_rollback_plan
from approval.verification_watcher import VerificationWatcher


class TestRollbackPlanner:
    def test_on_inverts_to_off(self):
        plan = build_rollback_plan(
            "app-1",
            [{"device_id": "zigbee.bulb", "action": "on"}],
            {"zigbee.bulb": {"on": False}},
        )
        assert plan.can_compensate is True
        assert plan.compensation_actions == [{"device_id": "zigbee.bulb", "action": "off", "params": {}, "delay_s": 0}]
        assert plan.irreversible_actions == []

    def test_lock_inverts_to_unlock(self):
        plan = build_rollback_plan(
            "app-1",
            [{"device_id": "zigbee.lock", "action": "lock"}],
            {"zigbee.lock": {"locked": True}},
        )
        assert plan.compensation_actions == [
            {"device_id": "zigbee.lock", "action": "unlock", "params": {}, "delay_s": 0}
        ]

    def test_ir_send_is_irreversible(self):
        plan = build_rollback_plan(
            "app-1",
            [{"device_id": "ir.hub", "action": "ir_send", "params": {"code": "power"}}],
            {},
        )
        assert plan.can_compensate is False
        assert len(plan.irreversible_actions) == 1

    def test_restore_brightness_from_state(self):
        plan = build_rollback_plan(
            "app-1",
            [{"device_id": "zigbee.bulb", "action": "set_brightness", "params": {"brightness": 255}}],
            {"zigbee.bulb": {"brightness": 100}},
        )
        assert plan.compensation_actions == [
            {"device_id": "zigbee.bulb", "action": "set_brightness", "params": {"brightness": 100}, "delay_s": 0}
        ]


class TestRollbackExecutor:
    @pytest.mark.asyncio
    async def test_execute_records_success(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            async def record_rollback(self, approval_id, trigger, status="success", error_message=None):
                self.calls.append((approval_id, trigger, status, error_message))
                return {"id": 1}

        async def executor(actions):
            return {"success": True, "executed": len(actions), "errors": []}

        client = FakeClient()
        plan = RollbackPlan(
            approval_id="app-1",
            can_compensate=True,
            compensation_actions=[{"device_id": "zigbee.bulb", "action": "off"}],
        )
        rex = RollbackExecutor(client, executor)
        result = await rex.execute(plan, trigger="human_reject")
        assert result["success"] is True
        assert result["executed"] == 1
        assert client.calls[0][2] == "success"


class TestVerificationWatcher:
    @pytest.mark.asyncio
    async def test_state_matches(self):
        async def lookup(device_id):
            return {"last_state": {"on": False}}

        watcher = VerificationWatcher(lookup)
        report = await watcher.verify("app-1", {"zigbee.bulb": {"on": False}})
        assert report["verified"] is True
        assert report["devices"]["zigbee.bulb"]["matches"] is True

    @pytest.mark.asyncio
    async def test_state_mismatch(self):
        async def lookup(device_id):
            return {"last_state": {"on": True}}

        watcher = VerificationWatcher(lookup)
        report = await watcher.verify("app-1", {"zigbee.bulb": {"on": False}})
        assert report["verified"] is False
        assert report["devices"]["zigbee.bulb"]["matches"] is False
