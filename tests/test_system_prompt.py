"""
Tests for system_prompt — OpenClaw section conditional inclusion.
"""
from system_prompt import build_system_message


class TestSystemPromptDefault:
    """By default, PC tools section should NOT appear."""

    def test_no_pc_section_by_default(self):
        msg = build_system_message()
        assert "PCツール" not in msg["content"]
        assert "OpenClaw" not in msg["content"]
        assert "run_pc_command" not in msg["content"]

    def test_base_tools_present(self):
        msg = build_system_message()
        assert "speak" in msg["content"]
        assert "create_task" in msg["content"]
        assert "get_zone_status" in msg["content"]

    def test_safety_rules_present(self):
        msg = build_system_message()
        assert "安全第一" in msg["content"]
        assert "CO2" in msg["content"]


class TestSystemPromptOpenClaw:
    """When openclaw_enabled=True, PC section should appear."""

    def test_pc_section_included(self):
        msg = build_system_message(openclaw_enabled=True)
        assert "PCツール（OpenClaw連携）" in msg["content"]

    def test_pc_tools_listed(self):
        msg = build_system_message(openclaw_enabled=True)
        assert "get_pc_status" in msg["content"]
        assert "run_pc_command" in msg["content"]
        assert "control_browser" in msg["content"]
        assert "send_pc_notification" in msg["content"]

    def test_pc_safety_rules_included(self):
        msg = build_system_message(openclaw_enabled=True)
        assert "PC安全ルール" in msg["content"]
        assert "rm -rf" in msg["content"]
        assert "GPU温度85度" in msg["content"]

    def test_base_tools_still_present(self):
        msg = build_system_message(openclaw_enabled=True)
        assert "speak" in msg["content"]
        assert "create_task" in msg["content"]

    def test_explicit_false_same_as_default(self):
        msg_default = build_system_message()
        msg_false = build_system_message(openclaw_enabled=False)
        assert msg_default["content"] == msg_false["content"]
