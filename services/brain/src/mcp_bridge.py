"""
MQTT <-> JSON-RPC 2.0 (MCP) bridge for device control.
"""
import asyncio
import json
import uuid
from loguru import logger

MCP_TIMEOUT = 10  # seconds


class MCPBridge:
    def __init__(self, mqtt_client):
        self.client = mqtt_client
        self._pending: dict[str, asyncio.Future] = {}

    def handle_response(self, topic: str, payload: dict):
        """Handle MCP response from a device."""
        request_id = payload.get("id")
        if request_id and request_id in self._pending:
            future = self._pending.pop(request_id)
            if not future.done():
                future.set_result(payload.get("result"))

    async def call_tool(self, agent_id: str, tool_name: str, arguments: dict) -> dict | None:
        """Send MCP tool call and wait for response."""
        request_id = str(uuid.uuid4())
        topic = f"mcp/{agent_id}/request/{tool_name}"
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": tool_name,
            "params": arguments,
        }

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future

        self.client.publish(topic, json.dumps(payload))
        logger.debug(f"MCP request sent: {agent_id}/{tool_name} id={request_id}")

        try:
            result = await asyncio.wait_for(future, timeout=MCP_TIMEOUT)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            logger.warning(f"MCP timeout: {agent_id}/{tool_name}")
            return None
