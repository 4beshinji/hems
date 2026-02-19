
import asyncio
import json
import random
from typing import Dict, Any

# Mock MQTT Client
class MockMQTT:
    def __init__(self):
        self.subscribers = {}

    def subscribe(self, topic, callback):
        self.subscribers[topic] = callback

    def publish(self, topic, payload):
        print(f"[MQTT] {topic}: {payload}")
        # Simple wildcard matching would be needed here for real simulation
        # For now, direct match
        if topic in self.subscribers:
            self.subscribers[topic](topic, payload)

mock_broker = MockMQTT()

# --- Mock Brain ---
async def brain_logic():
    print("Brain started.")
    # Subscribe to sensors
    def on_sensor(topic, msg):
        data = json.loads(msg)
        if data.get("temperature", 0) > 28:
            print("Brain: High Temp Detected! Calling AC...")
            mock_broker.publish("mcp/ac_01/request/call_tool", 
                                json.dumps({"method": "call_tool", "params": {"name": "turn_on", "arguments": {"temp": 24}}, "id": "req_1"}))
    
    mock_broker.subscribe("office/env/sensor_01/status", on_sensor)

# --- Mock Edge Device ---
async def sensor_node():
    print("Sensor Node started.")
    while True:
        temp = random.uniform(20, 30)
        mock_broker.publish("office/env/sensor_01/status", json.dumps({"temperature": temp}))
        await asyncio.sleep(2)

async def ac_node():
    print("AC Node started.")
    def on_request(topic, msg):
        print(f"AC Node received request: {msg}")
        # Respond
        mock_broker.publish("mcp/ac_01/response/req_1", json.dumps({"result": "ok", "id": "req_1"}))

    mock_broker.subscribe("mcp/ac_01/request/call_tool", on_request)

# --- Runner ---
async def main():
    await asyncio.gather(
        brain_logic(),
        sensor_node(),
        ac_node(),
        asyncio.sleep(10) # Run for 10 seconds
    )

if __name__ == "__main__":
    asyncio.run(main())
