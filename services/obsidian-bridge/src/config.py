"""
Configuration for Obsidian Bridge — environment variables.
"""

import os

from dotenv import load_dotenv

from hems_common import load_mqtt_config

load_dotenv()

# Vault path (mounted volume)
VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "/vault")

# MQTT — module-level constants kept for backward compat; loaded via hems_common
_mqtt = load_mqtt_config()
MQTT_BROKER = _mqtt.broker
MQTT_PORT = _mqtt.port
MQTT_USER = _mqtt.user
MQTT_PASS = _mqtt.password

# Watcher
WATCHER_DEBOUNCE = float(os.getenv("OBSIDIAN_WATCHER_DEBOUNCE", "2.0"))

# Index
MAX_SEARCH_RESULTS = int(os.getenv("OBSIDIAN_MAX_SEARCH_RESULTS", "10"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
