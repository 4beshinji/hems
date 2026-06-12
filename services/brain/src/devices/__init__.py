"""devices/ — vendor-agnostic device parsing + actuator dispatch (W3.4 split).

Canonical home for what was previously the ``device_dispatcher`` god-module.
The top-level ``device_dispatcher`` module remains as a backward-compatible
facade that re-exports the public surface from here.
"""

from __future__ import annotations

from devices.actions import (
    _ACTION_CAPABILITY,
    DEVICE_ALLOWED_ACTIONS,
    _ha_service_for,
    _switchbot_cmd_for,
    _zigbee_payload_for,
)
from devices.observation import _SENSOR_CHANNEL_UNITS, DeviceObservation
from devices.registry import VENDOR_PARSERS, DeviceDispatcher, parse_mqtt
from devices.vendors.zigbee import (
    is_raw_ieee_addr,
    parse_z2m_bridge_devices,
)

__all__ = [
    "DEVICE_ALLOWED_ACTIONS",
    "VENDOR_PARSERS",
    "_ACTION_CAPABILITY",
    "_SENSOR_CHANNEL_UNITS",
    "DeviceDispatcher",
    "DeviceObservation",
    "_ha_service_for",
    "_switchbot_cmd_for",
    "_zigbee_payload_for",
    "is_raw_ieee_addr",
    "parse_mqtt",
    "parse_z2m_bridge_devices",
]
