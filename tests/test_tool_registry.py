"""
Tests for tool_registry — OpenClaw tool conditional inclusion.
"""

from tool_dispatch import TOOL_HANDLERS
from tool_registry import CHAT_ALLOWED_TOOL_NAMES, get_chat_tools, get_tools

PC_TOOL_NAMES = {"get_pc_status", "run_pc_command", "control_browser", "send_pc_notification"}
BASE_TOOL_NAMES = {
    "create_task",
    "get_zone_status",
    "speak",
    "get_active_tasks",
    "get_device_status",
    "get_sensor_history",
    "control_actuator",
    "list_devices",
    "describe_device",
    "list_scenes",
    "execute_scene_by_name",
    "zigbee_permit_join",
}


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
        # All BASE + all PC tools must be present. Extra tools are allowed
        # because list_processes was added later under openclaw_enabled.
        assert len(tools) >= len(BASE_TOOL_NAMES) + len(PC_TOOL_NAMES)

    def test_base_tool_count(self):
        tools = get_tools(openclaw_enabled=False)
        assert len(tools) == len(BASE_TOOL_NAMES)


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


def test_all_enabled_tool_schemas_match_dispatch_handlers():
    tools = get_tools(
        openclaw_enabled=True,
        services_enabled=True,
        obsidian_enabled=True,
        ha_enabled=True,
        biometric_enabled=True,
        perception_enabled=True,
        shopping_enabled=True,
        switchbot_enabled=True,
        news_enabled=True,
        knowledge_enabled=True,
        gas_enabled=True,
        tapo_enabled=True,
        device_registry_enabled=True,
    )
    schema_names = {t["function"]["name"] for t in tools}
    assert schema_names == set(TOOL_HANDLERS)


def test_chat_allowlist_references_existing_tool_schemas():
    tools = get_tools(
        openclaw_enabled=True,
        services_enabled=True,
        obsidian_enabled=True,
        ha_enabled=True,
        biometric_enabled=True,
        perception_enabled=True,
        shopping_enabled=True,
        switchbot_enabled=True,
        news_enabled=True,
        knowledge_enabled=True,
        gas_enabled=True,
        tapo_enabled=True,
        device_registry_enabled=True,
    )
    schema_names = {t["function"]["name"] for t in tools}
    assert schema_names >= CHAT_ALLOWED_TOOL_NAMES


def test_chat_tools_do_not_include_mutating_actions():
    tools = get_chat_tools(
        openclaw_enabled=True,
        services_enabled=True,
        obsidian_enabled=True,
        ha_enabled=True,
        biometric_enabled=True,
        perception_enabled=True,
        switchbot_enabled=True,
        news_enabled=True,
        knowledge_enabled=True,
        gas_enabled=True,
        tapo_enabled=True,
        device_registry_enabled=True,
    )
    chat_names = {t["function"]["name"] for t in tools}
    mutating_names = {
        "add_shopping_item",
        "control_actuator",
        "control_browser",
        "control_climate",
        "control_cover",
        "control_light",
        "control_switch",
        "control_switchbot",
        "create_task",
        "execute_scene",
        "execute_scene_by_name",
        "run_pc_command",
        "send_pc_notification",
        "send_switchbot_ir",
        "set_guest_mode",
        "speak",
        "write_note",
        "zigbee_permit_join",
    }
    assert chat_names.isdisjoint(mutating_names)
