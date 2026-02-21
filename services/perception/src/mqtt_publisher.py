"""
MQTT publisher/subscriber for perception data.
Extended from biometric-bridge pattern with subscribe + callback support
for MCP camera response routing.
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
        self._message_callback = None

    def connect(self):
        self.client.on_message = self._on_message
        self.client.connect(self.broker, self.port)
        self.client.loop_start()
        logger.info(f"MQTT connected to {self.broker}:{self.port}")

    def publish(self, topic: str, data: dict, retain: bool = False):
        payload = json.dumps(data, ensure_ascii=False)
        self.client.publish(topic, payload, retain=retain)

    def subscribe(self, topic: str):
        self.client.subscribe(topic)
        logger.debug(f"MQTT subscribed to {topic}")

    def set_message_callback(self, callback):
        self._message_callback = callback

    def _on_message(self, client, userdata, msg):
        if self._message_callback:
            try:
                payload = json.loads(msg.payload.decode())
                self._message_callback(msg.topic, payload)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f"Failed to parse MQTT message on {msg.topic}: {e}")

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
