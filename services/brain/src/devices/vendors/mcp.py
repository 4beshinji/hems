"""MCP (physical sensor + actuator) vendor parser.

Sensor parsing is unchanged. Actuator control is now handled through
``control_actuator`` with ``action="mcp_call"`` instead of the legacy
``send_device_command`` tool.
"""

from __future__ import annotations

import json
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
        """Dispatch MCP actuator calls via the shared MCPBridge.

        ``control_actuator`` now handles MCP devices with ``action="mcp_call"``
        and ``params={"tool_name": ..., "arguments": {...}}``.
        """
        if action != "mcp_call":
            return {"success": False, "error": f"MCP devices only support mcp_call, got '{action}'"}
        if ctx.mcp_bridge is None:
            return {"success": False, "error": "MCP bridge not available"}

        tool_name = params.get("tool_name") or params.get("name")
        if not tool_name:
            return {"success": False, "error": "mcp_call requires params.tool_name"}
        arguments = params.get("arguments") or params.get("args") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except Exception:
                return {"success": False, "error": "mcp_call arguments must be valid JSON"}

        device_ref = device.get("vendor_ref") or device.get("device_id", "").replace("mcp.", "")
        result = await ctx.mcp_bridge.call_tool(device_ref, tool_name, arguments)
        if result is None:
            return {"success": False, "error": f"MCP call to {device_ref}/{tool_name} failed or timed out"}
        return {"success": True, "result": json.dumps(result, ensure_ascii=False)}
