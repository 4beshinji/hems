"""
Configuration for HEMS SwitchBot Bridge service.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# SwitchBot API v1.1
SWITCHBOT_TOKEN = os.getenv("SWITCHBOT_TOKEN", "")
SWITCHBOT_SECRET = os.getenv("SWITCHBOT_SECRET", "")
SWITCHBOT_API_BASE = "https://api.switch-bot.com/v1.1"

# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

# Device-to-zone mapping (JSON: {"DEVICE_ID": {"zone": "living_room", "name": "メインライト"}})
SWITCHBOT_DEVICE_MAP = os.getenv("SWITCHBOT_DEVICE_MAP", "{}")

# Polling interval (seconds)
POLL_INTERVAL = int(os.getenv("SWITCHBOT_POLL_INTERVAL", "30"))

# Webhook (optional — SwitchBot pushes state changes)
WEBHOOK_URL = os.getenv("SWITCHBOT_WEBHOOK_URL", "")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
