"""
Configuration for HEMS Home Assistant Bridge service.
"""

import os

from dotenv import load_dotenv

from hems_common.config import load_mqtt_config

load_dotenv()

# Home Assistant
HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")

# MQTT — loaded via hems_common for consistency with other bridges
_mqtt = load_mqtt_config()
MQTT_BROKER = _mqtt.broker
MQTT_PORT = _mqtt.port
MQTT_USER = _mqtt.user
MQTT_PASS = _mqtt.password

# Entity mapping (JSON string: {"entity_id": {"zone": "...", "domain": "..."}})
HEMS_HA_ENTITY_MAP = os.getenv("HEMS_HA_ENTITY_MAP", "{}")

# Polling interval (fallback when WebSocket disconnects)
STATE_POLL_INTERVAL = int(os.getenv("HEMS_HA_POLL_INTERVAL", "30"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
