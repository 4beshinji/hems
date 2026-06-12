"""
Device dispatcher — vendor-agnostic actuator control and topic parsing.

W3.4: this module is now a backward-compatible **facade**. The implementation
lives in the ``devices/`` sub-package (observation / actions / registry / base /
vendors/*). All public symbols are re-exported here so existing imports
(``from device_dispatcher import DeviceDispatcher / parse_mqtt /
parse_z2m_bridge_devices``) and module-level patch points
(``device_dispatcher.HA_BRIDGE_URL``, ``device_dispatcher.asyncio.sleep``)
keep working unchanged.

Two responsibilities (unchanged behaviour):
1. Parse incoming MQTT topic/payload → DeviceObservation for auto-registration
2. Execute action on a Device (DB row) → dispatch to the right bridge/MQTT publisher

The env-derived URLs and ``asyncio`` below are the authoritative live values:
``DispatchContext`` reads them back through this module so reassignment and test
patches remain in effect.
"""

from __future__ import annotations

# `asyncio` is re-exported intentionally: tapo/ha dispatch and tests patch
# `device_dispatcher.asyncio.sleep` / `.ensure_future`.
import asyncio  # noqa: F401
import os

# ── Public surface (re-exported from devices/) ─────────────────────
from devices import (
    _ACTION_CAPABILITY,  # noqa: F401
    _SENSOR_CHANNEL_UNITS,  # noqa: F401
    DEVICE_ALLOWED_ACTIONS,
    VENDOR_PARSERS,  # noqa: F401
    DeviceDispatcher,
    DeviceObservation,
    _ha_service_for,  # noqa: F401
    _switchbot_cmd_for,  # noqa: F401
    _zigbee_payload_for,  # noqa: F401
    is_raw_ieee_addr,  # noqa: F401
    parse_mqtt,
    parse_z2m_bridge_devices,
)

# Live, env-derived module globals (authoritative; DispatchContext reads them back).
HA_BRIDGE_URL = os.getenv("HA_BRIDGE_URL", "")
SWITCHBOT_BRIDGE_URL = os.getenv("SWITCHBOT_BRIDGE_URL", "")
TAPO_BRIDGE_URL = os.getenv("TAPO_BRIDGE_URL", "")
DASHBOARD_API_URL = os.getenv("DASHBOARD_API_URL", os.getenv("BACKEND_URL", "http://backend:8000"))

__all__ = [
    "DASHBOARD_API_URL",
    "DEVICE_ALLOWED_ACTIONS",
    "HA_BRIDGE_URL",
    "SWITCHBOT_BRIDGE_URL",
    "TAPO_BRIDGE_URL",
    "DeviceDispatcher",
    "DeviceObservation",
    "parse_mqtt",
    "parse_z2m_bridge_devices",
]
