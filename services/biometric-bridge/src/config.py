"""
Configuration for HEMS Biometric Bridge.
"""
import os

# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
MQTT_TOPIC_PREFIX = "hems/personal/biometrics"

# Provider
BIOMETRIC_PROVIDER = os.getenv("BIOMETRIC_PROVIDER", "gadgetbridge")

# Zepp Cloud API (optional)
ZEPP_ENABLED = os.getenv("ZEPP_ENABLED", "").lower() in ("true", "1", "yes")
ZEPP_EMAIL = os.getenv("ZEPP_EMAIL", "")
ZEPP_PASSWORD = os.getenv("ZEPP_PASSWORD", "")
ZEPP_POLL_INTERVAL = int(os.getenv("ZEPP_POLL_INTERVAL", "1800"))

# Fatigue calculation defaults
FATIGUE_HR_WEIGHT = float(os.getenv("FATIGUE_HR_WEIGHT", "0.3"))
FATIGUE_SLEEP_WEIGHT = float(os.getenv("FATIGUE_SLEEP_WEIGHT", "0.4"))
FATIGUE_STRESS_WEIGHT = float(os.getenv("FATIGUE_STRESS_WEIGHT", "0.3"))
