import asyncio
import aiohttp
import json
import os
import paho.mqtt.client as mqtt
import time
import sys

# Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_USER = os.getenv("MQTT_USER", "soms")
MQTT_PASS = os.getenv("MQTT_PASS", "soms_dev_mqtt")
API_URL = "http://localhost:8000"

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"Connected to MQTT with result code {rc}")

def on_publish(client, userdata, mid, reason_code=None, properties=None):
    print("Message Published")

async def check_tasks():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}/tasks/") as response:
            if response.status == 200:
                tasks = await response.json()
                print(f"Tasks found: {len(tasks)}")
                for t in tasks:
                    print(f" - {t['title']}: {t.get('description')} (Bounty: {t.get('bounty_gold')})")
                    if t['title'] == "Buy Coffee Beans":
                        return True
            else:
                print(f"Failed to fetch tasks: {response.status}")
    return False

def main():
    # 1. Publish Trigger
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_publish = on_publish
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    print("Connecting to MQTT...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    time.sleep(1)
    
    topic = "office/kitchen/coffee_machine/status"
    payload = json.dumps({"beans_level": 0})
    
    print(f"Publishing trigger to {topic}...")
    client.publish(topic, payload)
    
    # 2. Wait for Brain to process
    print("Waiting for Brain to process (10s)...")
    time.sleep(10)
    client.loop_stop()
    
    # 3. Verify via API
    try:
        success = asyncio.run(check_tasks())
        if success:
            print("SUCCESS: Human Task created successfully.")
            sys.exit(0)
        else:
            print("FAILURE: expected task not found.")
            sys.exit(1)
    except Exception as e:
        print(f"Error checking API: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
