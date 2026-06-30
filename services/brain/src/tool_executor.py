"""
Tool executor — routes tool calls through sanitizer to domain handler mixins.
"""

import asyncio
import os
from typing import Any

import aiohttp
from loguru import logger

from tool_dispatch import TOOL_HANDLERS
from tool_handlers_biometric import BiometricToolHandlers
from tool_handlers_core import CoreToolHandlers
from tool_handlers_device import DeviceToolHandlers
from tool_handlers_external import ExternalToolHandlers
from tool_handlers_home import HomeToolHandlers
from tool_handlers_pc import PCToolHandlers
from tool_handlers_perception import PerceptionToolHandlers
from tool_handlers_switchbot import SwitchBotToolHandlers
from tool_handlers_world import WorldToolHandlers

OPENCLAW_BRIDGE_URL = os.getenv("OPENCLAW_BRIDGE_URL", os.getenv("LOCALCRAW_BRIDGE_URL", ""))
OBSIDIAN_BRIDGE_URL = os.getenv("OBSIDIAN_BRIDGE_URL", "")
HA_BRIDGE_URL = os.getenv("HA_BRIDGE_URL", "")
BIOMETRIC_BRIDGE_URL = os.getenv("BIOMETRIC_BRIDGE_URL", "")
PERCEPTION_BRIDGE_URL = os.getenv("PERCEPTION_BRIDGE_URL", "")
SWITCHBOT_BRIDGE_URL = os.getenv("SWITCHBOT_BRIDGE_URL", "")
NEWS_BRIDGE_URL = os.getenv("NEWS_BRIDGE_URL", "")
KNOWLEDGE_BRIDGE_URL = os.getenv("KNOWLEDGE_BRIDGE_URL", "")
TAPO_BRIDGE_URL = os.getenv("TAPO_BRIDGE_URL", "")


class ToolExecutor(
    CoreToolHandlers,
    WorldToolHandlers,
    HomeToolHandlers,
    DeviceToolHandlers,
    ExternalToolHandlers,
    SwitchBotToolHandlers,
    PCToolHandlers,
    BiometricToolHandlers,
    PerceptionToolHandlers,
):
    def __init__(
        self,
        sanitizer,
        dashboard_client,
        world_model,
        task_queue,
        session: aiohttp.ClientSession = None,
        device_registry=None,
        device_dispatcher=None,
        scene_executor=None,
        persona_rewriter=None,
        power_mode_manager=None,
        event_writer=None,
    ):
        self.sanitizer = sanitizer
        self.dashboard = dashboard_client
        self.world_model = world_model
        self.task_queue = task_queue
        self._session = session
        self.device_registry = device_registry
        self.device_dispatcher = device_dispatcher
        self.scene_executor = scene_executor
        self.persona_rewriter = persona_rewriter
        self.power_mode_manager = power_mode_manager
        self.event_writer = event_writer
        self.openclaw_url = OPENCLAW_BRIDGE_URL
        self.obsidian_url = OBSIDIAN_BRIDGE_URL
        self.ha_url = HA_BRIDGE_URL
        self.biometric_url = BIOMETRIC_BRIDGE_URL
        self.perception_url = PERCEPTION_BRIDGE_URL
        self.switchbot_url = SWITCHBOT_BRIDGE_URL
        self.news_url = NEWS_BRIDGE_URL
        self.knowledge_url = KNOWLEDGE_BRIDGE_URL
        self.tapo_url = TAPO_BRIDGE_URL
        self.voice_url = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")
        self.dashboard_api_url = os.getenv("DASHBOARD_API_URL", "http://backend:8000")

        try:
            from motion_retriever import MotionRetriever

            self.motion_retriever = MotionRetriever()
        except Exception as e:
            logger.warning(f"Motion retriever init failed: {e}")
            self.motion_retriever = None

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call with sanitizer validation."""
        validation = self.sanitizer.validate_tool_call(tool_name, arguments)
        if not validation["allowed"]:
            logger.warning(f"Tool call REJECTED: {tool_name} - {validation['reason']}")
            return {"success": False, "error": validation["reason"]}

        try:
            handler_name = TOOL_HANDLERS.get(tool_name)
            if handler_name is None:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
            handler = getattr(self, handler_name)
            if tool_name == "get_active_tasks":
                return await handler()
            result = handler(arguments)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {"success": False, "error": str(e)}
