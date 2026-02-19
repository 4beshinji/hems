"""
MQTT publisher for HEMS HA Bridge.
"""
import json
import paho.mqtt.client as mqtt
from loguru import logger


class MQTTPublisher:
    def __init__(self, broker: str, port: int, user: str = "", password: str = ""):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if user:
            self.client.username_pw_set(user, password)
        self._broker = broker
        self._port = port

    def connect(self):
        try:
            self.client.connect(self._broker, self._port, 60)
            self.client.loop_start()
            logger.info(f"MQTT connected to {self._broker}:{self._port}")
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")

    def publish(self, topic: str, payload: dict):
        try:
            self.client.publish(topic, json.dumps(payload), retain=True)
        except Exception as e:
            logger.error(f"MQTT publish error: {e}")

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
