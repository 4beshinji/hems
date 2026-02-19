"""
Configuration for HEMS Home Assistant Bridge service.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Home Assistant
HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")

# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

# Entity mapping (JSON string: {"entity_id": {"zone": "...", "domain": "..."}})
HEMS_HA_ENTITY_MAP = os.getenv("HEMS_HA_ENTITY_MAP", "{}")

# Polling interval (fallback when WebSocket disconnects)
STATE_POLL_INTERVAL = int(os.getenv("HEMS_HA_POLL_INTERVAL", "30"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
