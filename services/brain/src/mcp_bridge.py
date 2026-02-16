
import asyncio
import json
import uuid
from typing import Dict, Any, Callable, Awaitable

class MCPBridge:
    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.tools: Dict[str, Dict[str, Any]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def call_tool(self, agent_id: str, tool_name: str, arguments: Dict[str, Any], timeout: float = None) -> Dict[str, Any]:
        request_id = str(uuid.uuid4())
        topic = f"mcp/{agent_id}/request/call_tool"

        payload = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": request_id
        }

        # Create a Future to await response
        self._loop = asyncio.get_running_loop()
        future = self._loop.create_future()
        self.pending_requests[request_id] = future

        # Publish request
        self.mqtt_client.publish(topic, json.dumps(payload))

        effective_timeout = timeout or 10.0
        try:
            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=effective_timeout)
            return response
        except asyncio.TimeoutError:
            del self.pending_requests[request_id]
            raise TimeoutError(f"Tool execution timed out ({effective_timeout}s): {tool_name} on {agent_id}")

    def handle_response(self, topic: str, payload: Dict[str, Any]):
        # Expected topic: mcp/{agent_id}/response/{request_id}
        parts = topic.split('/')
        if len(parts) < 4:
            return
            
        # JSON-RPC payload id is authoritative; topic is fallback
        request_id = payload.get("id", parts[3])
            
        if request_id in self.pending_requests:
            future = self.pending_requests.pop(request_id)
            if not future.done() and self._loop:
                if "error" in payload:
                    self._loop.call_soon_threadsafe(
                        future.set_exception, Exception(payload["error"])
                    )
                else:
                    self._loop.call_soon_threadsafe(
                        future.set_result, payload.get("result")
                    )
