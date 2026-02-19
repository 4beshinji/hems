"""
MQTT publisher for OpenClaw Bridge — publishes PC metrics to hems/pc/* topics.
"""
import json
import paho.mqtt.client as mqtt
from loguru import logger


class MQTTPublisher:
    """Publishes structured JSON to MQTT topics."""

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
            logger.info(f"MQTT connected: {self._broker}:{self._port}")
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            raise

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, topic: str, payload: dict):
        """Publish JSON payload to an MQTT topic."""
        try:
            self.client.publish(topic, json.dumps(payload), qos=0)
        except Exception as e:
            logger.debug(f"MQTT publish error on {topic}: {e}")
