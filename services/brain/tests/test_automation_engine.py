"""Tests for AutomationEngine trigger evaluation and firing."""

import pytest

from automation_engine import AutomationEngine


def _make_engine():
    """Create an AutomationEngine with mocked dependencies."""
    return AutomationEngine(
        dispatcher=None,
        scene_executor=None,
        dashboard_client=None,
        llm_client=None,
        world_model=None,
        sanitizer=None,
        approval_gate=None,
        implicit_detector=None,
    )


@pytest.fixture
def fired():
    """Shared list to capture fired rule IDs."""
    return []


@pytest.fixture
def engine(fired):
    """Engine with event rules and a mock _fire that records IDs."""
    rules = [
        {"id": 1, "enabled": True, "trigger_type": "event", "trigger_config": {"event": "wake_up"}, "actions": []},
        {"id": 2, "enabled": True, "trigger_type": "event", "trigger_config": {"event": "motion:*"}, "actions": []},
        {
            "id": 3,
            "enabled": True,
            "trigger_type": "event",
            "trigger_config": {"event": "motion:entrance"},
            "actions": [],
        },
        {"id": 4, "enabled": False, "trigger_type": "event", "trigger_config": {"event": "motion:*"}, "actions": []},
        {"id": 5, "enabled": True, "trigger_type": "sensor_threshold", "trigger_config": {}, "actions": []},
    ]
    eng = _make_engine()
    eng._rules = rules

    async def mock_fire(rule):
        fired.append(rule["id"])

    eng._fire = mock_fire
    return eng


class TestTriggerEvent:
    async def test_exact_match(self, engine, fired):
        await engine.trigger_event("wake_up")
        assert 1 in fired
        assert 2 not in fired
        assert 3 not in fired

    async def test_wildcard_match(self, engine, fired):
        await engine.trigger_event("motion:pir_entrance")
        assert 2 in fired
        assert 3 not in fired

    async def test_exact_and_wildcard_both_fire(self, engine, fired):
        await engine.trigger_event("motion:entrance")
        assert 2 in fired
        assert 3 in fired

    async def test_disabled_rule_not_fired(self, engine, fired):
        await engine.trigger_event("motion:anything")
        assert 4 not in fired
        assert 2 in fired

    async def test_non_event_rules_ignored(self, engine, fired):
        await engine.trigger_event("motion:anything")
        assert 5 not in fired

    async def test_no_match(self, engine, fired):
        await engine.trigger_event("unknown:event")
        assert not fired
