"""Configuration for HEMS News Bridge service."""

import os

from dotenv import load_dotenv

from hems_common import load_mqtt_config

load_dotenv()

# MQTT — module-level constants kept for backward compat; loaded via hems_common
_mqtt = load_mqtt_config()
MQTT_BROKER = _mqtt.broker
MQTT_PORT = _mqtt.port
MQTT_USER = _mqtt.user
MQTT_PASS = _mqtt.password

# Ollama
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5")
OLLAMA_SUMMARY_MODEL = os.getenv("OLLAMA_SUMMARY_MODEL", "") or OLLAMA_MODEL

# News sources
NEWS_SOURCES = os.getenv("NEWS_SOURCES", "nhk_main,nhk_international,bbc_world,guardian_world")
NEWS_SOURCE_LIST = [s.strip() for s in NEWS_SOURCES.split(",") if s.strip()]

# Daily summary schedule
NEWS_DAILY_HOUR = int(os.getenv("NEWS_DAILY_HOUR", "7"))
NEWS_DAILY_MINUTE = int(os.getenv("NEWS_DAILY_MINUTE", "30"))

# Urgent check polling interval (seconds)
NEWS_POLL_INTERVAL = int(os.getenv("NEWS_POLL_INTERVAL", "300"))

# Urgency threshold (0.0-1.0)
NEWS_URGENCY_THRESHOLD = float(os.getenv("NEWS_URGENCY_THRESHOLD", "0.8"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
