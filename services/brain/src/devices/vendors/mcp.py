"""MCP (physical sensor) vendor parser.

Parse-only: MCP actuator control is routed through the legacy
``send_device_command`` tool, so dispatch returns a fixed error (byte-stable).
"""

from __future__ import annotations

from typing import Any

from devices.base import DispatchContext, VendorParser
from devices.observation import _SENSOR_CHANNEL_UNITS, DeviceObservation


def _infer_sensor_class(channel: str) -> str:
    if channel in ("temperature", "humidity"):
        return "temp_humidity"
    if channel == "co2":
        return "co2"
    if channel == "soil_moisture":
        return "soil"
    if channel in ("light", "illuminance"):
        return "light_sensor"
    return "sensor"


class McpParser(VendorParser):
    vendor = "mcp"

    def matches(self, parts: list[str]) -> bool:
        # W3.8c: canonical prefix is hems/sensors/{zone}/sensor/{device_id}/{channel}
        return len(parts) >= 6 and parts[0] == "hems" and parts[1] == "sensors" and parts[3] == "sensor"

    def parse(self, parts: list[str], payload: dict) -> DeviceObservation | None:
        zone_id, device_name, channel = parts[2], parts[4], parts[5]
        device_id = f"mcp.{device_name}"
        value = payload.get(channel) or payload.get("value")
        last_value: dict[str, Any] = {}
        if value is not None:
            try:
                last_value[channel] = float(value)
            except (TypeError, ValueError):
                pass
        unit = _SENSOR_CHANNEL_UNITS.get(channel, "")
        return DeviceObservation(
            device_id=device_id,
            vendor="mcp",
            vendor_ref=device_name,
            kind="sensor",
            device_class=_infer_sensor_class(channel),
            channels=[channel],
            units={channel: unit} if unit else {},
            zone=zone_id,
            last_value=last_value,
        )

    async def dispatch(self, ctx: DispatchContext, device: dict, action: str, params: dict) -> dict[str, Any]:
        return {"success": False, "error": "MCP actuator control uses send_device_command tool"}
