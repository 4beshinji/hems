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
        self.connected = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if user:
            self.client.username_pw_set(user, password)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.reconnect_delay_set(min_delay=1, max_delay=60)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            logger.info(f"MQTT connected to {self.broker}:{self.port}")
        else:
            self.connected = False
            logger.warning(f"MQTT connect failed with rc={rc}")

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        self.connected = False
        if rc != 0:
            logger.warning(f"MQTT unexpected disconnect (rc={rc}), auto-reconnecting...")

    def connect(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def publish(self, topic: str, data: dict, retain: bool = False) -> bool:
        """Publish data to MQTT. Returns True on success."""
        if not self.connected:
            return False
        payload = json.dumps(data, ensure_ascii=False)
        result = self.client.publish(topic, payload, retain=retain)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        self.connected = False
