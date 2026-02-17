"""
Configuration for OpenClaw Bridge — resolved from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()

OPENCLAW_GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "ws://host.docker.internal:18789")
OPENCLAW_GATEWAY_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN", "")

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "hems")
MQTT_PASS = os.getenv("MQTT_PASS", "hems_dev_mqtt")

METRICS_INTERVAL = int(os.getenv("OPENCLAW_METRICS_INTERVAL", "10"))
PROCESS_INTERVAL = int(os.getenv("OPENCLAW_PROCESS_INTERVAL", "30"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# === Service Checkers ===
GMAIL_ENABLED = os.getenv("HEMS_GMAIL_ENABLED", "").lower() in ("1", "true")
GMAIL_EMAIL = os.getenv("HEMS_GMAIL_EMAIL", "")
GMAIL_APP_PASSWORD = os.getenv("HEMS_GMAIL_APP_PASSWORD", "")
GMAIL_INTERVAL = int(os.getenv("HEMS_GMAIL_INTERVAL", "300"))

GITHUB_ENABLED = os.getenv("HEMS_GITHUB_ENABLED", "").lower() in ("1", "true")
GITHUB_TOKEN = os.getenv("HEMS_GITHUB_TOKEN", "")
GITHUB_INTERVAL = int(os.getenv("HEMS_GITHUB_INTERVAL", "300"))

BROWSER_CHECKERS_JSON = os.getenv("HEMS_BROWSER_CHECKERS", "[]")
