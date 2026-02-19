"""
Configuration for Obsidian Bridge — environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Vault path (mounted volume)
VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "/vault")

# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

# Watcher
WATCHER_DEBOUNCE = float(os.getenv("OBSIDIAN_WATCHER_DEBOUNCE", "2.0"))

# Index
MAX_SEARCH_RESULTS = int(os.getenv("OBSIDIAN_MAX_SEARCH_RESULTS", "10"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
