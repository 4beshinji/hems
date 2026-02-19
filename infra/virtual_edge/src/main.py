
import os
import sys
import time
import logging
import json
import random
import paho.mqtt.client as mqtt
from device import VirtualDevice
from swarm_transport import VirtualTransport
from swarm_hub import VirtualSwarmHub
from swarm_leaf import TempHumidityLeaf, PIRLeaf, DoorSensorLeaf

# Config
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VirtualEdge")

devices = []

# --- Device Implementations ---

class SensorNode(VirtualDevice):
    def __init__(self, client):
        super().__init__("sensor_01", "office/main/sensor/sensor_01", client)
        self.state = {"temperature": 22.0, "humidity": 50.0}
        self.register_tool("get_status", self.get_status)

    def get_status(self):
        return dict(self.state)

    def update(self):
        # Random Walk
        self.state["temperature"] += random.uniform(-0.1, 0.1)
        self.state["humidity"] += random.uniform(-0.5, 0.5)
        self.publish_sensor_data(self.state)

class HydroNode(VirtualDevice):
    def __init__(self, client):
        super().__init__("hydro_01", "hydro/lettuce_raft", client)
        self.state = {"ph": 7.5, "ec": 1.2}
        self.register_tool("dose_ph_down", self.dose_ph_down)

    def dose_ph_down(self, amount_ml):
        # Simulate chemical reaction
        self.state["ph"] -= (amount_ml * 0.1)
        return {"status": "dosed", "new_ph_estimate": self.state["ph"]}

    def update(self):
        # pH naturally rises over time
        self.state["ph"] += 0.001
        self.publish_telemetry("status", self.state)

class AquaNode(VirtualDevice):
    def __init__(self, client):
        super().__init__("aqua_01", "aqua/main_tank", client)
        self.state = {"temp": 25.0, "lights": "on"}
        self.register_tool("set_lights", self.set_lights)
        self.register_tool("feed_fish", self.feed_fish)

    def set_lights(self, state):
        self.state["lights"] = state
        return {"status": "ok", "lights": state}

    def feed_fish(self):
        return {"status": "fed"}

    def update(self):
        self.publish_telemetry("status", self.state)

# --- Main ---

def on_connect(client, userdata, flags, rc, properties=None):
    logger.info(f"Connected to MQTT Broker with result code {rc}")
    for dev in devices:
        dev.subscribe()

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        topic = msg.topic
        for dev in devices:
            dev.handle_message(topic, payload)
    except Exception as e:
        logger.error(f"Msg Error: {e}")

def main():
    logger.info("Starting Virtual Edge Service...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_user = os.getenv("MQTT_USER")
    mqtt_pass = os.getenv("MQTT_PASS")
    if mqtt_user:
        client.username_pw_set(mqtt_user, mqtt_pass)
    client.on_connect = on_connect
    client.on_message = on_message

    # Register Devices
    devices.append(SensorNode(client))
    devices.append(HydroNode(client))
    devices.append(AquaNode(client))

    # --- SensorSwarm ---
    swarm_transport = VirtualTransport(name="swarm_main")

    leaf_env = TempHumidityLeaf(leaf_id=1, transport=swarm_transport, report_interval=10)
    leaf_env.name = "leaf_env_01"
    leaf_pir = PIRLeaf(leaf_id=2, transport=swarm_transport, report_interval=5)
    leaf_pir.name = "leaf_pir_01"
    leaf_door = DoorSensorLeaf(leaf_id=3, transport=swarm_transport, report_interval=15)
    leaf_door.name = "leaf_door_01"

    swarm_hub = VirtualSwarmHub(
        hub_id="swarm_hub_01",
        zone="main",
        mqtt_client=client,
        transport=swarm_transport,
        leaves=[leaf_env, leaf_pir, leaf_door],
    )
    devices.append(swarm_hub)

    # Connect
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            break
        except:
            logger.warning("Waiting for MQTT...")
            time.sleep(2)

    client.loop_start()

    # Simulation Loop
    while True:
        for dev in devices:
            dev.update()
        time.sleep(2.0) # Update simulation every 2s

if __name__ == "__main__":
    main()
