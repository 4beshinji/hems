"""
Configuration for HEMS Perception Service.
"""

import json
import os

# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

# Camera configuration — JSON array
# [{"device_id":"cam01","zone":"living_room","type":"mcp"},
#  {"device_id":"cam02","zone":"bedroom","type":"stream","url":"rtsp://..."}]
_cameras_raw = os.getenv("HEMS_PERCEPTION_CAMERAS", "[]")
try:
    CAMERAS: list[dict] = json.loads(_cameras_raw)
except json.JSONDecodeError:
    CAMERAS = []

# YOLO model settings
PERCEPTION_MODEL = os.getenv("HEMS_PERCEPTION_MODEL", "yolo11s.pt")
POSE_MODEL = os.getenv("HEMS_PERCEPTION_POSE_MODEL", "yolo11s-pose.pt")
CONFIDENCE_THRESHOLD = float(os.getenv("HEMS_PERCEPTION_CONFIDENCE", "0.5"))

# Processing interval (seconds)
PROCESS_INTERVAL = int(os.getenv("HEMS_PERCEPTION_INTERVAL", "5"))

# VLM (Vision Language Model) — disabled by default.
# Default backend: llama.cpp `vlm-light` / `vlm-heavy` services (OpenAI-compat).
# Legacy fallback: if VLM_LIGHT_API_URL is unset and VLM_OLLAMA_URL is given,
# we treat the Ollama URL as an OpenAI-compat base (`/v1` is appended by the
# analyzer). Ollama 0.1.26+ exposes `/v1/chat/completions`.
VLM_ENABLED = os.getenv("VLM_ENABLED", "false").lower() == "true"
_ollama_fallback = os.getenv("VLM_OLLAMA_URL", "").rstrip("/")
_ollama_fallback_v1 = f"{_ollama_fallback}/v1" if _ollama_fallback else ""
VLM_LIGHT_API_URL = (
    os.getenv("VLM_LIGHT_API_URL", "").rstrip("/")
    or _ollama_fallback_v1
    or "http://vlm-light:8080/v1"
)
VLM_HEAVY_API_URL = (
    os.getenv("VLM_HEAVY_API_URL", "").rstrip("/")
    or _ollama_fallback_v1
    or "http://vlm-heavy:8080/v1"
)
VLM_LIGHT_MODEL = os.getenv("VLM_LIGHT_MODEL", "minicpm-v")
VLM_HEAVY_MODEL = os.getenv("VLM_HEAVY_MODEL", "qwen2-vl-7b")
VLM_BASE_INTERVAL = int(os.getenv("VLM_BASE_INTERVAL", "1800"))
VLM_MIN_INTERVAL = int(os.getenv("VLM_MIN_INTERVAL", "60"))
VLM_MAX_INTERVAL = int(os.getenv("VLM_MAX_INTERVAL", "7200"))
VLM_BOOST_DURATION = int(os.getenv("VLM_BOOST_DURATION", "300"))
VLM_TIMEOUT = int(os.getenv("VLM_TIMEOUT", "30"))
VLM_MAX_TOKENS = int(os.getenv("VLM_MAX_TOKENS", "256"))
VLM_IMAGE_MAX_SIZE = int(os.getenv("VLM_IMAGE_MAX_SIZE", "512"))
LLM_MODEL = os.getenv("LLM_MODEL", "")

# Log level
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
