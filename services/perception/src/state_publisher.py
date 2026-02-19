"""
State Publisher - MQTT経由で解析結果を送信
"""
import json
import logging
import os
import paho.mqtt.client as mqtt
from typing import Any, Dict

logger = logging.getLogger(__name__)

class StatePublisher:
    _instance = None

    @classmethod
    def get_instance(cls, broker: str = "localhost", port: int = 1883):
        if cls._instance is None:
            cls._instance = cls(broker, port)
        return cls._instance

    def __init__(self, broker: str = "localhost", port: int = 1883):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqtt_user = os.getenv("MQTT_USER")
        mqtt_pass = os.getenv("MQTT_PASS")
        if mqtt_user:
            self.client.username_pw_set(mqtt_user, mqtt_pass)
        self.client.connect(broker, port)
        self.client.loop_start()
        logger.info(f"StatePublisher connected to {broker}:{port}")
    
    async def publish(self, topic: str, payload: Dict[str, Any]):
        """
        MQTT メッセージ送信
        
        Args:
            topic: MQTTトピック
            payload: 送信データ（JSON化される）
        """
        message = json.dumps(payload)
        result = self.client.publish(topic, message)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f"Published to {topic}: {payload}")
        else:
            logger.error(f"Failed to publish to {topic}")
