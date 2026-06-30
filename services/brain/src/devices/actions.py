"""Action allowlist + capability map + per-vendor command builders.

``DEVICE_ALLOWED_ACTIONS`` is the single source of truth for the
``control_actuator`` action allowlist (renamed from ``ALLOWED_ACTIONS`` in
W3.4). ``device_control_validator`` imports it so the two never drift.
"""

from __future__ import annotations

DEVICE_ALLOWED_ACTIONS = {
    "on",
    "off",
    "toggle",
    "set_brightness",
    "set_color_temp",
    "set_color_xy",
    "set_color_hs",
    "set_position",
    "set_temperature",
    "pulse",
    "rainbow",
    "ir_send",
    # MCP legacy tool unified into control_actuator
    "mcp_call",
}

_ACTION_CAPABILITY = {
    "on": "on_off",
    "off": "on_off",
    "toggle": "on_off",
    "set_brightness": "brightness",
    "set_color_temp": "color_temp",
    "set_color_xy": "color_xy",
    "set_color_hs": "color_hs",
    "set_position": "set_position",
    "set_temperature": "set_temperature",
    "pulse": "pulse",
    "rainbow": "color_hs",
    "ir_send": "ir_send",
}


def _ha_service_for(action: str, params: dict, domain: str) -> tuple[str | None, dict]:
    if action == "on":
        return f"{domain}/turn_on", {}
    if action == "off":
        return f"{domain}/turn_off", {}
    if action == "toggle":
        return f"{domain}/toggle", {}
    if action == "set_brightness":
        return "light/turn_on", {"brightness": int(params.get("value", 128))}
    if action == "set_color_temp":
        return "light/turn_on", {"color_temp": int(params.get("value", 300))}
    if action == "set_color_xy":
        return "light/turn_on", {"xy_color": [float(params.get("x", 0.3)), float(params.get("y", 0.3))]}
    if action == "set_color_hs":
        return "light/turn_on", {"hs_color": [float(params.get("hue", 0)), float(params.get("saturation", 100))]}
    if action == "set_position":
        return "cover/set_cover_position", {"position": int(params.get("value", 100))}
    if action == "set_temperature":
        return "climate/set_temperature", {"temperature": float(params.get("value", 24))}
    return None, {}


def _switchbot_cmd_for(action: str, params: dict) -> tuple[str | None, str, str]:
    if action == "on":
        return "turnOn", "default", "command"
    if action == "off":
        return "turnOff", "default", "command"
    if action == "toggle":
        return "toggle", "default", "command"
    if action == "set_brightness":
        return "setBrightness", str(params.get("value", 50)), "command"
    if action == "set_color_temp":
        return "setColorTemperature", str(params.get("value", 3000)), "command"
    if action == "set_position":
        return "setPosition", f"0,ff,{params.get('value', 50)}", "command"
    if action == "ir_send":
        return params.get("command", "turnOn"), params.get("parameter", "default"), "customize"
    return None, "", ""


def _zigbee_payload_for(action: str, params: dict) -> dict | None:
    if action == "on":
        return {"state": "ON"}
    if action == "off":
        return {"state": "OFF"}
    if action == "toggle":
        return {"state": "TOGGLE"}
    if action == "set_brightness":
        return {"state": "ON", "brightness": int(params.get("value", 128))}
    if action == "set_color_temp":
        return {"color_temp": int(params.get("value", 300))}
    if action == "set_color_xy":
        return {"color": {"x": float(params.get("x", 0.3)), "y": float(params.get("y", 0.3))}}
    if action == "set_color_hs":
        return {"color": {"hue": float(params.get("hue", 0)), "saturation": float(params.get("saturation", 100))}}
    if action == "pulse":
        return {"state": "ON"}  # pulse itself is handled separately
    return None
