"""Shared config helpers for HEMS bridges (shallow dataclass + loaders).

Promotes tapo-bridge's ``_load_json_env`` to a shared ``load_json_env`` and
provides a minimal MQTT config dataclass. Kept intentionally shallow: bridges
keep exporting their own module-level constants and use these as building
blocks (W3.2 migrates incrementally, behaviour-preserving).
"""

import json
import os
from dataclasses import dataclass


@dataclass
class MqttConfig:
    """Common MQTT connection settings shared by all bridges."""

    broker: str = "mosquitto"
    port: int = 1883
    user: str = ""
    password: str = ""


def load_mqtt_config(*, default_user: str = "") -> MqttConfig:
    """Load MQTT settings from the standard env vars.

    Honours ``MQTT_BROKER`` / ``MQTT_PORT`` / ``MQTT_USER`` / ``MQTT_PASS``.
    ``default_user`` covers bridges (e.g. tapo) with a non-empty default user.
    """
    return MqttConfig(
        broker=os.getenv("MQTT_BROKER", "mosquitto"),
        port=int(os.getenv("MQTT_PORT", "1883")),
        user=os.getenv("MQTT_USER", default_user),
        password=os.getenv("MQTT_PASS", ""),
    )


def load_json_env(key: str, default: str = "{}") -> dict:
    """Parse a JSON object from env var ``key``.

    Returns ``{}`` on empty/blank or invalid JSON (never raises). Promoted
    from tapo-bridge's ``_load_json_env``.
    """
    raw = os.getenv(key, default)
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
