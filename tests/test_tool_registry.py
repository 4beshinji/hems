"""
Tests for tool_registry — OpenClaw tool conditional inclusion.
"""
from tool_registry import get_tools

PC_TOOL_NAMES = {"get_pc_status", "run_pc_command", "control_browser", "send_pc_notification"}
BASE_TOOL_NAMES = {"create_task", "send_device_command", "get_zone_status", "speak", "get_active_tasks", "get_device_status"}


class TestToolRegistryDefault:
    """By default, PC tools should NOT be included."""

    def test_default_returns_base_tools_only(self):
        tools = get_tools()
        names = {t["function"]["name"] for t in tools}
        assert names == BASE_TOOL_NAMES

    def test_default_no_pc_tools(self):
        tools = get_tools()
        names = {t["function"]["name"] for t in tools}
        assert names.isdisjoint(PC_TOOL_NAMES)

    def test_explicit_false_same_as_default(self):
        tools = get_tools(openclaw_enabled=False)
        names = {t["function"]["name"] for t in tools}
        assert names == BASE_TOOL_NAMES


class TestToolRegistryOpenClawEnabled:
    """When openclaw_enabled=True, PC tools should be included."""

    def test_includes_pc_tools(self):
        tools = get_tools(openclaw_enabled=True)
        names = {t["function"]["name"] for t in tools}
        assert PC_TOOL_NAMES.issubset(names)

    def test_still_includes_base_tools(self):
        tools = get_tools(openclaw_enabled=True)
        names = {t["function"]["name"] for t in tools}
        assert BASE_TOOL_NAMES.issubset(names)

    def test_total_tool_count(self):
        tools = get_tools(openclaw_enabled=True)
        assert len(tools) == 10

    def test_base_tool_count(self):
        tools = get_tools(openclaw_enabled=False)
        assert len(tools) == 6


class TestToolRegistrySchemaValidity:
    """Verify all tool definitions follow OpenAI function-calling schema."""

    def test_all_tools_have_type_function(self):
        for enabled in (True, False):
            for tool in get_tools(openclaw_enabled=enabled):
                assert tool["type"] == "function"
                assert "function" in tool
                assert "name" in tool["function"]
                assert "description" in tool["function"]
                assert "parameters" in tool["function"]

    def test_required_fields_present(self):
        for tool in get_tools(openclaw_enabled=True):
            params = tool["function"]["parameters"]
            assert params["type"] == "object"
            assert "properties" in params
