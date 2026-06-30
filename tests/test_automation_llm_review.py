"""
Regression tests for AutomationEngine._llm_review.

chat() returns an LLMResponse object, not a str. A prior bug treated the
response as a string ((response or "").strip() / .splitlines()), which raised
AttributeError and forced every llm_review-mode rule to silently skip. These
tests confirm a "fire" verdict is honoured and a real LLM error skips cleanly.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from automation_engine import AutomationEngine
from llm_client import LLMResponse


def _make_engine(llm_response):
    llm_client = MagicMock()
    llm_client.chat = AsyncMock(return_value=llm_response)
    world_model = MagicMock()
    world_model.get_llm_context = MagicMock(return_value="state")
    return AutomationEngine(
        dispatcher=MagicMock(),
        scene_executor=MagicMock(),
        dashboard_client=MagicMock(),
        llm_client=llm_client,
        world_model=world_model,
        sanitizer=MagicMock(),
    )


@pytest.mark.asyncio
async def test_llm_review_fire_verdict_honoured():
    engine = _make_engine(LLMResponse(content="fire\n発火が適切です"))
    should_fire, reason = await engine._llm_review({"name": "rule"})
    assert should_fire is True
    assert "発火" in reason


@pytest.mark.asyncio
async def test_llm_review_skip_verdict_honoured():
    engine = _make_engine(LLMResponse(content="skip\n雨予報のため"))
    should_fire, reason = await engine._llm_review({"name": "rule"})
    assert should_fire is False
    assert "雨" in reason


@pytest.mark.asyncio
async def test_llm_review_error_response_skips_without_raising():
    engine = _make_engine(LLMResponse(error="HTTP 500"))
    should_fire, reason = await engine._llm_review({"name": "rule"})
    assert should_fire is False
    assert "HTTP 500" in reason


@pytest.mark.asyncio
async def test_fire_routes_require_confirm_rule_through_approval_gate():
    scene_executor = MagicMock()
    scene_executor.execute = AsyncMock(return_value={"success": True, "executed": 1, "errors": []})
    approval_gate = MagicMock()
    approval_gate.execute_rule = AsyncMock(
        return_value={"success": True, "executed": 1, "errors": [], "approval_status": "approved"}
    )
    engine = AutomationEngine(
        dispatcher=MagicMock(),
        scene_executor=scene_executor,
        dashboard_client=MagicMock(),
        llm_client=MagicMock(),
        world_model=MagicMock(),
        sanitizer=MagicMock(),
        approval_gate=approval_gate,
    )

    rule = {
        "id": 1,
        "name": "lock door",
        "enabled": True,
        "trigger_type": "event",
        "trigger_config": {"event": "leave"},
        "actions": [{"device_id": "zigbee.lock", "action": "lock"}],
        "require_confirm": True,
    }
    await engine._fire(rule)
    approval_gate.execute_rule.assert_awaited_once_with(rule)
    scene_executor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_fire_executes_low_risk_rule_directly_when_gate_present():
    scene_executor = MagicMock()
    scene_executor.execute = AsyncMock(return_value={"success": True, "executed": 1, "errors": []})
    approval_gate = MagicMock()
    approval_gate.execute_rule = AsyncMock()
    engine = AutomationEngine(
        dispatcher=MagicMock(),
        scene_executor=scene_executor,
        dashboard_client=MagicMock(),
        llm_client=MagicMock(),
        world_model=MagicMock(),
        sanitizer=MagicMock(),
        approval_gate=approval_gate,
    )

    rule = {
        "id": 2,
        "name": "night light",
        "enabled": True,
        "trigger_type": "event",
        "trigger_config": {"event": "bedtime"},
        "actions": [{"device_id": "zigbee.bulb", "action": "on"}],
        "require_confirm": False,
    }
    await engine._fire(rule)
    scene_executor.execute.assert_awaited_once()
    approval_gate.execute_rule.assert_not_awaited()
