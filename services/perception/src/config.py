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

# RTMO pose model (rtmlib / ONNX Runtime, Apache-2.0). Default = rtmo-s (CPU).
# Baked into the image at build time; override to a local .onnx path or another
# rtmo-{s,m,l} url. See services/perception/NOTICE for attribution.
POSE_MODEL = os.getenv(
    "HEMS_PERCEPTION_POSE_MODEL",
    "https://download.openmmlab.com/mmpose/v1/projects/rtmo/onnx_sdk/"
    "rtmo-s_8xb32-600e_body7-640x640-dac2bf74_20231211.zip",
)
# Inference device for onnxruntime: "cpu" (default) or "cuda". AMD ROCm EP is
# immature — keep CPU; GPU load belongs to the VLM (Ollama) path.
POSE_DEVICE = os.getenv("HEMS_PERCEPTION_DEVICE", "cpu")
CONFIDENCE_THRESHOLD = float(os.getenv("HEMS_PERCEPTION_CONFIDENCE", "0.5"))

# Processing interval (seconds)
PROCESS_INTERVAL = int(os.getenv("HEMS_PERCEPTION_INTERVAL", "5"))

# VLM (Vision Language Model) — disabled by default
VLM_ENABLED = os.getenv("VLM_ENABLED", "false").lower() == "true"
VLM_OLLAMA_URL = os.getenv("VLM_OLLAMA_URL", "http://ollama:11434")
VLM_LIGHT_MODEL = os.getenv("VLM_LIGHT_MODEL", "moondream")
VLM_HEAVY_MODEL = os.getenv("VLM_HEAVY_MODEL", "minicpm-v")
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
