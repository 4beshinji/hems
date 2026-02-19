"""
Configuration for HEMS GAS Bridge service.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# GAS Web App
GAS_WEBAPP_URL = os.getenv("GAS_WEBAPP_URL", "")
GAS_API_KEY = os.getenv("GAS_API_KEY", "")

# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

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
