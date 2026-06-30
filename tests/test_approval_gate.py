"""Tests for brain-side approval gate (Phase 0 HITL)."""

import pytest

from approval.gate import ApprovalGate


class _FakeClient:
    def __init__(self, decisions):
        self.decisions = decisions
        self.calls = []
        self._approval_counter = 0

    async def create(self, **kwargs):
        self._approval_counter += 1
        self.calls.append(("create", kwargs))
        return {"id": f"app-{self._approval_counter}"}

    async def get(self, approval_id):
        return self.decisions.get(approval_id)

    async def poll_decision(self, approval_id, **kwargs):
        return self.decisions.get(approval_id, {"status": "expired", "id": approval_id})

    async def record_snapshot(self, approval_id, entity_type, entity_id, before_state, after_state=None):
        self.calls.append(("snapshot", approval_id, entity_type, entity_id, before_state, after_state))
        return {"id": 1}

    async def mark_executed(self, approval_id):
        self.calls.append(("mark_executed", approval_id))
        return {"id": approval_id, "executed_at": "2026-01-01T00:00:00"}

    async def record_rollback(self, approval_id, trigger, status="success", error_message=None):
        self.calls.append(("rollback", approval_id, trigger, status))
        return {"id": 1}


@pytest.fixture
def low_risk_rule():
    return {
        "id": 1,
        "name": "夜間照明",
        "actions": [{"device_id": "zigbee.bulb_bedroom", "action": "on"}],
    }


@pytest.fixture
def high_risk_rule():
    return {
        "id": 2,
        "name": "ドアロック",
        "actions": [{"device_id": "zigbee.door_lock", "action": "lock"}],
    }


@pytest.mark.asyncio
async def test_low_risk_rule_executes_directly(low_risk_rule):
    async def executor(actions):
        return {"success": True, "executed": len(actions)}

    gate = ApprovalGate(client=_FakeClient({}), executor=executor)
    result = await gate.execute_rule(low_risk_rule)
    assert result["success"] is True
    assert result["executed"] == 1
    assert "approval_id" not in result


@pytest.mark.asyncio
async def test_high_risk_rule_awaits_approval_and_executes(high_risk_rule):
    async def executor(actions):
        return {"success": True, "executed": len(actions)}

    fake_client = _FakeClient({"app-1": {"id": "app-1", "status": "approved"}})
    gate = ApprovalGate(client=fake_client, executor=executor)
    result = await gate.execute_rule(high_risk_rule)
    assert result["success"] is True
    assert result["approval_status"] == "approved"
    assert result["approval_id"] == "app-1"
    assert any(c[0] == "mark_executed" for c in fake_client.calls)


@pytest.mark.asyncio
async def test_high_risk_rule_rejected_does_not_execute(high_risk_rule):
    async def executor(actions):
        return {"success": True, "executed": len(actions)}

    fake_client = _FakeClient({"app-1": {"id": "app-1", "status": "rejected"}})
    gate = ApprovalGate(client=fake_client, executor=executor)
    result = await gate.execute_rule(high_risk_rule)
    assert result["success"] is False
    assert result["approval_status"] == "rejected"
    assert result["executed"] == 0
    assert not any(c[0] == "rollback" for c in fake_client.calls)
    assert not any(c[0] == "mark_executed" for c in fake_client.calls)


@pytest.mark.asyncio
async def test_modified_payload_executes_modified_actions(high_risk_rule):
    async def executor(actions):
        return {"success": True, "executed": len(actions), "modified_action": actions[0].get("action")}

    fake_client = _FakeClient(
        {
            "app-1": {
                "id": "app-1",
                "status": "modified",
                "proposed_payload": {"actions": [{"device_id": "zigbee.door_lock", "action": "unlock"}]},
            }
        }
    )
    gate = ApprovalGate(client=fake_client, executor=executor)
    result = await gate.execute_rule(high_risk_rule)
    assert result["success"] is True
    assert result["approval_status"] == "modified"
    assert result["modified_action"] == "unlock"


@pytest.mark.asyncio
async def test_rejected_rule_does_not_trigger_rollback_executor(high_risk_rule):
    async def executor(actions):
        return {"success": True, "executed": len(actions)}

    async def state_lookup(device_id):
        return {"last_state": {"locked": False}}

    class FakeRollbackExecutor:
        def __init__(self):
            self.calls = []

        async def execute(self, plan, trigger):
            self.calls.append((plan.approval_id, plan.compensation_actions, trigger))
            return {"success": True, "executed": 1}

    fake_client = _FakeClient({"app-1": {"id": "app-1", "status": "rejected"}})
    rollback = FakeRollbackExecutor()
    gate = ApprovalGate(
        client=fake_client,
        executor=executor,
        state_lookup=state_lookup,
        rollback_executor=rollback,
    )
    result = await gate.execute_rule(high_risk_rule)
    assert result["success"] is False
    assert result["approval_status"] == "rejected"
    assert "rollback" not in result
    assert len(rollback.calls) == 0


@pytest.mark.asyncio
async def test_approved_execution_failure_does_not_mark_executed(high_risk_rule):
    async def executor(actions):
        return {"success": False, "executed": 0, "errors": ["device offline"]}

    fake_client = _FakeClient({"app-1": {"id": "app-1", "status": "approved"}})
    gate = ApprovalGate(client=fake_client, executor=executor)
    result = await gate.execute_rule(high_risk_rule)
    assert result["success"] is False
    assert result["approval_status"] == "approved"
    assert result["executed"] == 0
    assert not any(c[0] == "mark_executed" for c in fake_client.calls)


@pytest.mark.asyncio
async def test_modified_execution_failure_does_not_mark_executed(high_risk_rule):
    async def executor(actions):
        return {"success": False, "executed": 0, "errors": ["device offline"]}

    fake_client = _FakeClient(
        {
            "app-1": {
                "id": "app-1",
                "status": "modified",
                "proposed_payload": {"actions": [{"device_id": "zigbee.door_lock", "action": "unlock"}]},
            }
        }
    )
    gate = ApprovalGate(client=fake_client, executor=executor)
    result = await gate.execute_rule(high_risk_rule)
    assert result["success"] is False
    assert result["approval_status"] == "modified"
    assert result["executed"] == 0
    assert not any(c[0] == "mark_executed" for c in fake_client.calls)
