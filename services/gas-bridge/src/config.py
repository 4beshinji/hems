"""
Configuration for HEMS GAS Bridge service.
"""

import os

from dotenv import load_dotenv
from hems_common import load_mqtt_config

load_dotenv()

# GAS Web App
GAS_WEBAPP_URL = os.getenv("GAS_WEBAPP_URL", "")
GAS_API_KEY = os.getenv("GAS_API_KEY", "")

# MQTT — module-level constants kept for backward compat; loaded via hems_common
_mqtt = load_mqtt_config()
MQTT_BROKER = _mqtt.broker
MQTT_PORT = _mqtt.port
MQTT_USER = _mqtt.user
MQTT_PASS = _mqtt.password

# Polling intervals (seconds)
CALENDAR_INTERVAL = int(os.getenv("HEMS_GAS_CALENDAR_INTERVAL", "120"))
TASKS_INTERVAL = int(os.getenv("HEMS_GAS_TASKS_INTERVAL", "300"))
GMAIL_INTERVAL = int(os.getenv("HEMS_GAS_GMAIL_INTERVAL", "300"))
SHEETS_INTERVAL = int(os.getenv("HEMS_GAS_SHEETS_INTERVAL", "600"))
DRIVE_INTERVAL = int(os.getenv("HEMS_GAS_DRIVE_INTERVAL", "600"))

# Sheets to monitor (comma-separated: "name1:id1:sheet1:range1,name2:id2:sheet2:range2")
# Example: "budget:1xABC:Sheet1:A1:D20,tracker:1xDEF:Data:A:C"
SHEETS_CONFIG = os.getenv("HEMS_GAS_SHEETS", "")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
