"""Environment-based config loader for tapo-bridge."""

import os
from dataclasses import dataclass

from hems_common import load_json_env


@dataclass
class Config:
    # Credentials for Tapo/Kasa cloud auth (required for Tapo P110, P125M, L530 etc.)
    tapo_username: str
    tapo_password: str
    # Device map: {"plug_desklight": "192.168.1.42", "plug_pump": "192.168.1.43"}
    # Keys are vendor_ref (flat, no prefix) — the brain uses "tapo.<key>" as device_id.
    devices: dict[str, str]
    # Optional per-device zone map: {"plug_desklight": "bedroom"}
    zones: dict[str, str]
    # Optional per-device friendly names
    names: dict[str, str]
    poll_interval_sec: int
    mqtt_broker: str
    mqtt_port: int
    mqtt_user: str
    mqtt_pass: str


def load_config() -> Config:
    return Config(
        tapo_username=os.getenv("TAPO_USERNAME", ""),
        tapo_password=os.getenv("TAPO_PASSWORD", ""),
        devices=load_json_env("TAPO_DEVICES"),
        zones=load_json_env("TAPO_ZONES"),
        names=load_json_env("TAPO_NAMES"),
        poll_interval_sec=int(os.getenv("TAPO_POLL_INTERVAL", "30")),
        mqtt_broker=os.getenv("MQTT_BROKER", "mosquitto"),
        mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
        mqtt_user=os.getenv("MQTT_USER", "hems-tapo-bridge"),
        mqtt_pass=os.getenv("MQTT_PASS", ""),
    )
