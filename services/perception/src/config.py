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

# Log level
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
