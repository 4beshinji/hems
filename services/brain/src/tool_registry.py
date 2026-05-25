"""
OpenAI function-calling tool definitions for HEMS Brain.
Base: create_task, send_device_command, get_zone_status, speak, get_active_tasks, get_device_status
OpenClaw: get_pc_status, run_pc_command, control_browser, send_pc_notification
Obsidian: search_notes, write_note, get_recent_notes
Knowledge: search_knowledge, get_knowledge_sources, read_knowledge_document
"""

from tool_schemas.base import get_base_tools
from tool_schemas.biometric import _get_biometric_tools
from tool_schemas.core import _get_service_tools, _get_shopping_tools, _get_system_tools
from tool_schemas.device import _get_device_registry_tools
from tool_schemas.external import _get_gas_tools, _get_knowledge_tools, _get_news_tools, _get_obsidian_tools
from tool_schemas.home import _get_ha_tools, _get_scene_tools, _get_tapo_tools
from tool_schemas.pc import _get_pc_tools
from tool_schemas.perception import _get_perception_tools
from tool_schemas.switchbot import _get_switchbot_tools

CHAT_ALLOWED_TOOL_NAMES = {
    "get_zone_status",
    "get_active_tasks",
    "get_device_status",
    "get_sensor_history",
    "get_pc_status",
    "get_service_status",
    "search_notes",
    "get_recent_notes",
    "list_note_tags",
    "get_home_devices",
    "get_sensor_data",
    "get_weather",
    "get_biometrics",
    "get_sleep_summary",
    "get_biometric_trend",
    "get_sleep_history",
    "get_perception_status",
    "list_cameras",
    "get_vlm_status",
    "get_activity_history",
    "list_scene_objects",
    "get_scene_timeline",
    "get_shopping_list",
    "get_switchbot_devices",
    "get_news_summary",
    "search_knowledge",
    "get_knowledge_sources",
    "read_knowledge_document",
    "get_recent_knowledge_changes",
    "get_recent_emails",
    "gas_query_free_slots",
    "gas_query_sheet",
    "get_entity_status",
    "get_power_consumption",
    "list_processes",
    "list_devices",
    "describe_device",
    "list_scenes",
}


def get_tools(
    openclaw_enabled: bool = False,
    services_enabled: bool = False,
    obsidian_enabled: bool = False,
    ha_enabled: bool = False,
    biometric_enabled: bool = False,
    perception_enabled: bool = False,
    shopping_enabled: bool = False,
    switchbot_enabled: bool = False,
    news_enabled: bool = False,
    knowledge_enabled: bool = False,
    gas_enabled: bool = False,
    tapo_enabled: bool = False,
    device_registry_enabled: bool = True,
) -> list:
    tools = get_base_tools()

    if openclaw_enabled:
        tools.extend(_get_pc_tools())

    if services_enabled:
        tools.extend(_get_service_tools())

    if obsidian_enabled:
        tools.extend(_get_obsidian_tools())

    if ha_enabled:
        tools.extend(_get_ha_tools())
        tools.extend(_get_system_tools())

    if biometric_enabled:
        tools.extend(_get_biometric_tools())

    if perception_enabled:
        tools.extend(_get_perception_tools())

    if shopping_enabled:
        tools.extend(_get_shopping_tools())

    if switchbot_enabled:
        tools.extend(_get_switchbot_tools())

    if news_enabled:
        tools.extend(_get_news_tools())

    if knowledge_enabled:
        tools.extend(_get_knowledge_tools())

    if gas_enabled:
        tools.extend(_get_gas_tools())

    if tapo_enabled:
        tools.extend(_get_tapo_tools())

    if device_registry_enabled:
        tools.extend(_get_device_registry_tools())
        tools.extend(_get_scene_tools())

    return tools


def get_chat_tools(
    openclaw_enabled: bool = False,
    services_enabled: bool = False,
    obsidian_enabled: bool = False,
    ha_enabled: bool = False,
    biometric_enabled: bool = False,
    perception_enabled: bool = False,
    switchbot_enabled: bool = False,
    news_enabled: bool = False,
    knowledge_enabled: bool = False,
    gas_enabled: bool = False,
    tapo_enabled: bool = False,
    device_registry_enabled: bool = True,
) -> list:
    """Return read-only tool subset for conversational chat.

    Excludes action tools: create_task, speak, send_device_command, control_*,
    write_note, add_shopping_item, run_pc_command, etc.
    """
    all_tools = get_tools(
        openclaw_enabled=openclaw_enabled,
        services_enabled=services_enabled,
        obsidian_enabled=obsidian_enabled,
        ha_enabled=ha_enabled,
        biometric_enabled=biometric_enabled,
        perception_enabled=perception_enabled,
        device_registry_enabled=device_registry_enabled,
        shopping_enabled=True,
        switchbot_enabled=switchbot_enabled,
        news_enabled=news_enabled,
        knowledge_enabled=knowledge_enabled,
        gas_enabled=gas_enabled,
        tapo_enabled=tapo_enabled,
    )
    return [t for t in all_tools if t["function"]["name"] in CHAT_ALLOWED_TOOL_NAMES]


def get_tool_names(
    openclaw_enabled: bool = False,
    services_enabled: bool = False,
    obsidian_enabled: bool = False,
    ha_enabled: bool = False,
    biometric_enabled: bool = False,
    perception_enabled: bool = False,
    shopping_enabled: bool = False,
    switchbot_enabled: bool = False,
    news_enabled: bool = False,
    knowledge_enabled: bool = False,
) -> list:
    """Return list of all enabled tool names."""
    return [
        t["function"]["name"]
        for t in get_tools(
            openclaw_enabled,
            services_enabled,
            obsidian_enabled,
            ha_enabled,
            biometric_enabled,
            perception_enabled,
            shopping_enabled,
            switchbot_enabled,
            news_enabled,
            knowledge_enabled,
        )
    ]
