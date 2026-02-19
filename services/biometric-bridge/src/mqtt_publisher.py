"""
MQTT publisher for biometric data (same pattern as HA bridge).
"""
import json
import paho.mqtt.client as mqtt
from loguru import logger


class MQTTPublisher:
    def __init__(self, broker: str, port: int, user: str = "", password: str = ""):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if user:
            self.client.username_pw_set(user, password)

    def connect(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()
        logger.info(f"MQTT connected to {self.broker}:{self.port}")

    def publish(self, topic: str, data: dict, retain: bool = False):
        payload = json.dumps(data, ensure_ascii=False)
        self.client.publish(topic, payload, retain=retain)

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
