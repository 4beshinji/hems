"""
HEMS Lite Sentinel — configuration via environment variables.
"""
import os
import json

# --- Site identity ---
SITE_ID = os.getenv("SITE_ID", "hems-lite")
SITE_NAME = os.getenv("SITE_NAME", "HEMS Lite")

# --- Operation mode ---
# standalone: notifications only, no main HEMS connection
# satellite:  forward all data to main HEMS via MQTT bridge
# hybrid:     standalone normally, escalate CRITICAL to main HEMS
MODE = os.getenv("HEMS_LITE_MODE", "standalone")

# --- MQTT ---
MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

# --- Notifier ---
NOTIFIER_URL = os.getenv("NOTIFIER_URL", "http://notifier:8000")

# --- LLM Escalation (cloud API for gray zone) ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # openai | anthropic
LLM_API_URL = os.getenv("LLM_API_URL", "")  # e.g. https://api.openai.com/v1
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
# For Anthropic:
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Budget: max LLM calls per day (cost control)
LLM_DAILY_BUDGET = int(os.getenv("LLM_DAILY_BUDGET", "50"))
# Cooldown between escalations for same pattern (seconds)
LLM_ESCALATION_COOLDOWN = int(os.getenv("LLM_ESCALATION_COOLDOWN", "600"))

# --- Cycle timing ---
CYCLE_INTERVAL = int(os.getenv("SENTINEL_CYCLE_INTERVAL", "60"))
DAILY_SUMMARY_ENABLED = os.getenv("DAILY_SUMMARY_ENABLED", "true").lower() == "true"
DAILY_SUMMARY_TIME = os.getenv("DAILY_SUMMARY_TIME", "08:00")

# --- Biometric thresholds ---
# Critical (no cooldown, immediate)
HR_CRITICAL_HIGH = int(os.getenv("HR_CRITICAL_HIGH", "150"))
HR_CRITICAL_LOW = int(os.getenv("HR_CRITICAL_LOW", "40"))
SPO2_CRITICAL = int(os.getenv("SPO2_CRITICAL", "88"))

# High priority (5min cooldown)
HR_HIGH = int(os.getenv("HR_HIGH", "120"))
HR_LOW = int(os.getenv("HR_LOW", "45"))
SPO2_LOW = int(os.getenv("SPO2_LOW", "92"))
STRESS_HIGH = int(os.getenv("STRESS_HIGH", "80"))
BODY_TEMP_HIGH = float(os.getenv("BODY_TEMP_HIGH", "37.5"))
RESPIRATORY_RATE_HIGH = int(os.getenv("RESPIRATORY_RATE_HIGH", "25"))
HRV_LOW = int(os.getenv("HRV_LOW", "20"))

# Normal (30min cooldown)
SEDENTARY_ALERT_MINUTES = int(os.getenv("SEDENTARY_ALERT_MINUTES", "90"))
FATIGUE_HIGH = int(os.getenv("FATIGUE_HIGH", "70"))

# Environment
TEMP_HIGH = float(os.getenv("TEMP_HIGH", "32"))
TEMP_LOW = float(os.getenv("TEMP_LOW", "10"))
TEMP_WARN_HIGH = float(os.getenv("TEMP_WARN_HIGH", "28"))
TEMP_WARN_LOW = float(os.getenv("TEMP_WARN_LOW", "16"))
HUMIDITY_HIGH = float(os.getenv("HUMIDITY_HIGH", "70"))
HUMIDITY_LOW = float(os.getenv("HUMIDITY_LOW", "30"))
CO2_HIGH = int(os.getenv("CO2_HIGH", "1000"))
CO2_CRITICAL = int(os.getenv("CO2_CRITICAL", "1500"))

# Activity monitoring
ABSENCE_ALERT_MINUTES = int(os.getenv("ABSENCE_ALERT_MINUTES", "120"))
NIGHT_ACTIVITY_START = os.getenv("NIGHT_ACTIVITY_START", "02:00")
NIGHT_ACTIVITY_END = os.getenv("NIGHT_ACTIVITY_END", "05:00")
LYING_DAYTIME_MINUTES = int(os.getenv("LYING_DAYTIME_MINUTES", "180"))

# --- Gray zone thresholds (sub-threshold combinations) ---
# Multiplier: if individual value >= threshold * GRAY_ZONE_FACTOR, it's "warm"
GRAY_ZONE_FACTOR = float(os.getenv("GRAY_ZONE_FACTOR", "0.7"))
# Minimum number of simultaneous "warm" signals to trigger gray zone
GRAY_ZONE_MIN_SIGNALS = int(os.getenv("GRAY_ZONE_MIN_SIGNALS", "2"))
# Trend: consecutive readings in same direction
TREND_WINDOW_HOURS = int(os.getenv("TREND_WINDOW_HOURS", "24"))
# Behavior pattern deviation threshold (minutes)
PATTERN_DEVIATION_MINUTES = int(os.getenv("PATTERN_DEVIATION_MINUTES", "90"))

# --- Notification ---
NOTIFY_MIN_LEVEL = os.getenv("NOTIFY_MIN_LEVEL", "HIGH")  # CRITICAL|HIGH|NORMAL|INFO

# --- Perception (optional) ---
PERCEPTION_ENABLED = os.getenv("PERCEPTION_ENABLED", "false").lower() == "true"

# --- Biometric bridge ---
BIOMETRIC_BRIDGE_URL = os.getenv("BIOMETRIC_BRIDGE_URL", "")

# --- HA bridge ---
HA_BRIDGE_URL = os.getenv("HA_BRIDGE_URL", "")

# --- Alert cooldowns (seconds) ---
COOLDOWN_CRITICAL = 0          # no cooldown
COOLDOWN_HIGH = 300            # 5 minutes
COOLDOWN_NORMAL = 1800         # 30 minutes
COOLDOWN_INFO = 86400          # daily
COOLDOWN_GRAY_ZONE = 600      # 10 minutes

# --- Database ---
DB_PATH = os.getenv("SENTINEL_DB_PATH", "/data/sentinel.db")
