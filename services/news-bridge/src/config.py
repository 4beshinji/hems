"""Configuration for HEMS News Bridge service."""
import os
from dotenv import load_dotenv

load_dotenv()

# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

# LLM (OpenAI-compatible, defaults to llama.cpp `llm` service)
# Precedence: NEWS_LLM_API_URL > LLM_API_URL > OLLAMA_URL (legacy).
# NEWS_LLM_API_URL is a bare base URL; `/v1` is appended by the client.
LLM_API_URL = os.getenv("NEWS_LLM_API_URL", "") \
    or os.getenv("LLM_API_URL", "") \
    or os.getenv("OLLAMA_URL", "http://llm:8080")
LLM_MODEL = os.getenv("NEWS_LLM_MODEL", "") \
    or os.getenv("LLM_MODEL", "") \
    or os.getenv("OLLAMA_MODEL", "qwen2.5-14b-instruct")
LLM_SUMMARY_MODEL = os.getenv("NEWS_LLM_SUMMARY_MODEL", "") \
    or os.getenv("OLLAMA_SUMMARY_MODEL", "") \
    or LLM_MODEL

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
