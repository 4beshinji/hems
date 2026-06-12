"""DeviceObservation dataclass + sensor channel unit table.

Home (canonical) for the parsed-MQTT observation type. Re-exported by the
``device_dispatcher`` facade for backward-compatible imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeviceObservation:
    """Parsed from MQTT topic/payload, used for auto-registration heartbeat."""

    device_id: str
    vendor: str
    vendor_ref: str | None = None
    kind: str = "actuator"
    device_class: str | None = None
    capabilities: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    zone: str | None = None
    display_name: str | None = None
    description: str | None = None
    model_id: str | None = None
    manufacturer: str | None = None
    last_state: dict[str, Any] = field(default_factory=dict)
    last_value: dict[str, Any] = field(default_factory=dict)
    battery_pct: int | None = None
    link_quality: int | None = None
    last_seen_ts: float | None = None


_SENSOR_CHANNEL_UNITS = {
    "temperature": "°C",
    "humidity": "%",
    "co2": "ppm",
    "pressure": "hPa",
    "light": "lx",
    "illuminance": "lx",
    "voc": "",
    "soil_moisture": "%",
    "pm25": "µg/m³",
}


def _extract_sensor_values(payload: dict) -> dict[str, Any]:
    """Shared sensor-value extraction (switchbot + ha)."""
    values = {}
    for k in (
        "temperature",
        "humidity",
        "co2",
        "pressure",
        "light",
        "illuminance",
        "voc",
        "soil_moisture",
        "pm25",
        "power_watts",
        "voltage",
        "current",
        "energy_kwh",
        "power",
    ):
        if k in payload:
            values[k] = payload[k]
    return values
