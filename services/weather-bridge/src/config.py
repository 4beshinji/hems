"""
Configuration for HEMS Weather Bridge service.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Weather API provider: "jma" (気象庁, free, no key) or "openweathermap"
WEATHER_PROVIDER = os.getenv("WEATHER_PROVIDER", "jma")

# JMA settings (気象庁)
# Area code: see https://www.jma.go.jp/bosai/common/const/area.json
# Default: 130000 (東京都)
JMA_AREA_CODE = os.getenv("JMA_AREA_CODE", "130000")
# Detailed forecast area code (e.g., 130010 = 東京地方)
JMA_DETAIL_CODE = os.getenv("JMA_DETAIL_CODE", "130010")

# OpenWeatherMap settings
OWM_API_KEY = os.getenv("OWM_API_KEY", "")
OWM_LAT = os.getenv("OWM_LAT", "35.6762")
OWM_LON = os.getenv("OWM_LON", "139.6503")
OWM_UNITS = os.getenv("OWM_UNITS", "metric")
OWM_LANG = os.getenv("OWM_LANG", "ja")

# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

# Polling intervals (seconds)
CURRENT_INTERVAL = int(os.getenv("HEMS_WEATHER_CURRENT_INTERVAL", "600"))
FORECAST_INTERVAL = int(os.getenv("HEMS_WEATHER_FORECAST_INTERVAL", "1800"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
