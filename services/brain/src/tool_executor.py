"""
Tool executor — routes tool calls through sanitizer to handlers.
Forked from SOMS: removed wallet integration.
"""
import json
from loguru import logger


class ToolExecutor:
    def __init__(self, sanitizer, mcp_bridge, dashboard_client, world_model,
                 task_queue, session, device_registry):
        self.sanitizer = sanitizer
        self.mcp = mcp_bridge
        self.dashboard = dashboard_client
        self.world_model = world_model
        self.task_queue = task_queue
        self.session = session
        self.device_registry = device_registry

    async def execute(self, tool_name: str, arguments: dict) -> dict:
        """Execute a tool call with sanitizer validation."""
        # Validate through sanitizer
        validation = self.sanitizer.validate_tool_call(tool_name, arguments)
        if not validation["allowed"]:
            return {"success": False, "error": validation["reason"]}

        try:
            if tool_name == "create_task":
                return await self._handle_create_task(arguments)
            elif tool_name == "send_device_command":
                return await self._handle_device_command(arguments)
            elif tool_name == "get_zone_status":
                return await self._handle_get_zone_status(arguments)
            elif tool_name == "speak":
                return await self._handle_speak(arguments)
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {"success": False, "error": str(e)}

    async def _handle_create_task(self, args: dict) -> dict:
        result = await self.dashboard.create_task(args)
        if result:
            return {"success": True, "result": f"Task created: {result.get('title', '')} (id={result.get('id', '')})"}
        return {"success": False, "error": "Failed to create task"}

    async def _handle_device_command(self, args: dict) -> dict:
        agent_id = args.get("agent_id", "")
        tool_name = args.get("tool_name", "")
        tool_args = args.get("arguments", {})

        result = await self.mcp.call_tool(agent_id, tool_name, tool_args)
        if result is not None:
            return {"success": True, "result": json.dumps(result, ensure_ascii=False)}
        return {"success": False, "error": f"MCP call to {agent_id}/{tool_name} failed or timed out"}

    async def _handle_get_zone_status(self, args: dict) -> dict:
        zone_id = args.get("zone_id", "")
        zone = self.world_model.zones.get(zone_id)
        if not zone:
            return {"success": False, "error": f"Zone '{zone_id}' not found"}

        env = zone.environment
        status = {
            "zone_id": zone_id,
            "temperature": env.temperature,
            "humidity": env.humidity,
            "co2": env.co2,
            "occupancy_count": zone.occupancy.count if zone.occupancy else 0,
            "recent_events": [
                {"type": e.event_type, "description": e.description, "severity": e.severity}
                for e in zone.events[-5:]
            ],
        }
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    async def _handle_speak(self, args: dict) -> dict:
        message = args.get("message", "")
        zone = args.get("zone", "")
        tone = args.get("tone", "neutral")

        result = await self.dashboard.speak(message, zone, tone)
        if result:
            return {"success": True, "result": f"Spoke: {message[:50]}"}
        return {"success": False, "error": "Speak failed"}
