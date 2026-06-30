"""Tests for brain-side action / rule risk classifier (Phase 0 HITL)."""

from approval.action_risk_classifier import (
    classify_action,
    classify_rule,
    override_if_stricter,
)


class TestClassifyRule:
    def test_explicit_low_reversible_light(self):
        rule = {
            "name": "夜間照明",
            "risk_tier": "low",
            "reversibility": "reversible",
            "approval_required": False,
            "actions": [{"device_id": "zigbee.bulb_bedroom", "action": "on"}],
        }
        c = classify_rule(rule)
        assert c.risk_tier == "low"
        assert c.reversibility == "reversible"
        assert c.approval_required is False

    def test_explicit_critical_requires_approval(self):
        rule = {
            "name": "緊急ガス遮断",
            "risk_tier": "critical",
            "reversibility": "irreversible",
            "approval_required": True,
            "actions": [{"device_id": "zigbee.gas_valve", "action": "off"}],
        }
        c = classify_rule(rule)
        assert c.risk_tier == "critical"
        assert c.reversibility == "irreversible"
        assert c.approval_required is True

    def test_implicit_high_from_lock_device(self):
        rule = {
            "name": "外出時ロック",
            "actions": [{"device_id": "zigbee.door_lock", "action": "lock"}],
        }
        c = classify_rule(rule)
        assert c.risk_tier == "high"
        assert c.approval_required is True

    def test_implicit_critical_from_leak_keyword(self):
        rule = {
            "name": "漏水検知時止水",
            "actions": [{"device_id": "zigbee.water_valve", "action": "off"}],
        }
        c = classify_rule(rule)
        assert c.risk_tier == "critical"
        assert c.approval_required is True

    def test_irreversible_approval_override(self):
        rule = {
            "name": "メッセージ送信",
            "risk_tier": "low",
            "reversibility": "irreversible",
            "approval_required": False,
            "actions": [{"device_id": "notify.phone", "action": "message_send", "params": {"text": "hello"}}],
        }
        c = classify_rule(rule)
        assert c.approval_required is True
        assert c.reversibility == "irreversible"


class TestClassifyAction:
    def test_simple_light_action(self):
        c = classify_action({"device_id": "zigbee.bulb_living", "action": "on"})
        assert c.risk_tier == "low"
        assert c.reversibility == "reversible"
        assert c.approval_required is False

    def test_critical_alert_action(self):
        c = classify_action({"device_id": "notify.phone", "action": "alert", "params": {"message": "help"}})
        assert c.risk_tier == "critical"
        assert c.approval_required is True

    def test_fan_false_positive_avoided(self):
        c = classify_action({"device_id": "fantasy_lamp", "action": "on"})
        assert c.risk_tier == "low"
        assert c.approval_required is False

    def test_fan_legitimate_match(self):
        c = classify_action({"device_id": "livingroom_fan", "action": "on"})
        assert c.risk_tier == "high"
        assert c.approval_required is True

    def test_co_false_positive_avoided(self):
        c = classify_action({"device_id": "coffee_maker", "action": "on"})
        assert c.risk_tier == "low"
        assert c.approval_required is False

    def test_lock_false_positive_avoided(self):
        c = classify_action({"device_id": "clock", "action": "on"})
        assert c.risk_tier == "low"
        assert c.approval_required is False


class TestOverrideIfStricter:
    def test_override_to_high(self):
        base = classify_action({"device_id": "zigbee.bulb_living", "action": "on"})
        c = override_if_stricter(base, require_confirm=True, explicit_tier="high")
        assert c.risk_tier == "high"
        assert c.approval_required is True

    def test_no_relaxation(self):
        base = classify_action({"device_id": "zigbee.gas_valve", "action": "off"})
        c = override_if_stricter(base, explicit_tier="low")
        assert c.risk_tier == "critical"
