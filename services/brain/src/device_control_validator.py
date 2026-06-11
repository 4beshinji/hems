"""
device_control_validator -- shared action/params validation for device control.

Extracted from Sanitizer._validate_control_actuator so that both the LLM path
(sanitizer.validate_tool_call → _validate_control_actuator) and the REST path
(brain_chat_server._handle_device_control) run identical checks.

Callers:
  - services/brain/src/sanitizer.py           (LLM / tool-call path)
  - services/brain/src/brain_chat_server.py   (HTTP REST path via /devices/{id}/control)
"""

from typing import Any


def validate_device_control(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Validate *action* and *params* for a device control request.

    Returns ``{"allowed": True, "reason": ""}`` on success or
    ``{"allowed": False, "reason": "<message>"}`` on failure.

    The ``ALLOWED_ACTIONS`` set is imported from ``device_dispatcher`` so
    there is a single source of truth for which actions are permitted.
    """
    # Action allowlist is owned by device_dispatcher (single source of truth).
    from device_dispatcher import ALLOWED_ACTIONS

    if action not in ALLOWED_ACTIONS:
        return {"allowed": False, "reason": f"action '{action}' not in {sorted(ALLOWED_ACTIONS)}"}

    if params is None:
        params = {}

    if action == "pulse":
        duration = params.get("duration_s")
        if duration is None:
            return {"allowed": False, "reason": "pulse requires params.duration_s"}
        try:
            d = int(duration)
        except (TypeError, ValueError):
            return {"allowed": False, "reason": "pulse.duration_s must be integer"}
        if not (1 <= d <= 600):
            return {"allowed": False, "reason": f"pulse.duration_s {d} out of range (1-600)"}
    elif action == "set_brightness":
        v = params.get("value")
        if v is None or not (0 <= int(v) <= 255):
            return {"allowed": False, "reason": "set_brightness.value must be 0-255"}
    elif action == "set_color_temp":
        v = params.get("value")
        if v is None or not (153 <= int(v) <= 500):
            return {"allowed": False, "reason": "set_color_temp.value must be 153-500"}
    elif action == "set_color_xy":
        x = params.get("x")
        y = params.get("y")
        if x is None or y is None:
            return {"allowed": False, "reason": "set_color_xy requires params.x and params.y"}
        if not (0.0 <= float(x) <= 1.0 and 0.0 <= float(y) <= 1.0):
            return {"allowed": False, "reason": "set_color_xy x/y must be 0.0-1.0"}
    elif action == "set_color_hs":
        hue = params.get("hue")
        sat = params.get("saturation")
        if hue is None or sat is None:
            return {"allowed": False, "reason": "set_color_hs requires params.hue and params.saturation"}
        if not (0 <= float(hue) <= 360 and 0 <= float(sat) <= 100):
            return {"allowed": False, "reason": "set_color_hs hue must be 0-360, saturation 0-100"}
    elif action == "set_position":
        v = params.get("value")
        if v is None or not (0 <= int(v) <= 100):
            return {"allowed": False, "reason": "set_position.value must be 0-100"}
    elif action == "set_temperature":
        v = params.get("value")
        if v is None or not (16 <= float(v) <= 30):
            return {"allowed": False, "reason": "set_temperature.value must be 16-30"}
    elif action == "rainbow":
        duration = params.get("duration_s")
        if duration is None:
            return {"allowed": False, "reason": "rainbow requires params.duration_s"}
        try:
            d = int(duration)
        except (TypeError, ValueError):
            return {"allowed": False, "reason": "rainbow.duration_s must be integer"}
        if not (1 <= d <= 60):
            return {"allowed": False, "reason": f"rainbow.duration_s {d} out of range (1-60)"}

    return {"allowed": True, "reason": ""}
