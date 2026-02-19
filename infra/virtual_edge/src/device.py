import json
import logging
import random
import time
from typing import Dict, Any, Callable

logger = logging.getLogger(__name__)

class VirtualDevice:
    def __init__(self, device_id: str, topic_prefix: str, mqtt_client):
        self.device_id = device_id
        self.topic_prefix = topic_prefix
        self.client = mqtt_client
        self.tools: Dict[str, Callable] = {}
        self.state: Dict[str, Any] = {}

    def register_tool(self, name: str, callback: Callable):
        self.tools[name] = callback

    def subscribe(self):
        topic = f"mcp/{self.device_id}/request/call_tool"
        self.client.subscribe(topic)
        logger.info(f"[{self.device_id}] Subscribed to {topic}")

    def handle_message(self, topic: str, payload: dict):
        if topic == f"mcp/{self.device_id}/request/call_tool":
            self.handle_tool_call(payload)

    def handle_tool_call(self, payload: dict):
        req_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if method == "call_tool" and tool_name in self.tools:
            logger.info(f"[{self.device_id}] Tool Call: {tool_name} with {args}")
            try:
                # Simulate processing delay
                time.sleep(0.5)
                
                result = self.tools[tool_name](**args)
                
                response = {
                    "jsonrpc": "2.0",
                    "result": result,
                    "id": req_id
                }
                self.client.publish(f"mcp/{self.device_id}/response/{req_id}", json.dumps(response))
                
            except Exception as e:
                logger.error(f"Error executing tool: {e}")
                error_resp = {
                     "jsonrpc": "2.0",
                     "error": str(e),
                     "id": req_id
                }
                self.client.publish(f"mcp/{self.device_id}/response/{req_id}", json.dumps(error_resp))

    def update(self):
        """Called every loop to simulate physics/publishing"""
        pass
    
    def publish_telemetry(self, subtopic: str, data: dict):
        self.client.publish(f"{self.topic_prefix}/{subtopic}", json.dumps(data))

    def publish_sensor_data(self, data: dict):
        """Publish per-channel telemetry with {"value": X} for WorldModel."""
        for channel, value in data.items():
            self.client.publish(
                f"{self.topic_prefix}/{channel}",
                json.dumps({"value": value}),
            )
