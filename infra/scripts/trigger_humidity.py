
import paho.mqtt.client as mqtt
import json
import time
import os
import sys

# Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER", "soms")
MQTT_PASS = os.getenv("MQTT_PASS", "soms_dev_mqtt")
TOPIC = "office/meeting_room/sensor/hum_01/humidity"

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Connected to MQTT Broker!")
    else:
        print(f"Failed to connect, return code {rc}")

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    print(f"Connecting to MQTT Broker at {MQTT_BROKER}:{MQTT_PORT}...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    client.loop_start()
    time.sleep(1) # Wait for connection

    # Send Low Humidity Signal
    payload = {"value": 25.0, "unit": "%"}
    print(f"Publishing low humidity to {TOPIC}: {payload}")
    client.publish(TOPIC, json.dumps(payload))

    # Give it a moment to ensure message is sent
    time.sleep(2)
    
    client.loop_stop()
    client.disconnect()
    print("Done.")

if __name__ == "__main__":
    main()
