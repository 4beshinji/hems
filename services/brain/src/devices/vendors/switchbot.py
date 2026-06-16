"""SwitchBot vendor parser + dispatch."""

from __future__ import annotations

from typing import Any

import aiohttp

from devices.actions import _switchbot_cmd_for
from devices.base import DispatchContext, VendorParser
from devices.observation import DeviceObservation, _extract_sensor_values
from tool_http import internal_headers


def _infer_switchbot_class(payload: dict) -> str:
    t = (payload.get("device_type") or payload.get("domain") or "").lower()
    if "plug" in t:
        return "plug"
    if "light" in t or "bulb" in t:
        return "light"
    if "hub" in t:
        return "hub_ir"
    if "curtain" in t or "blind" in t:
        return "curtain"
    if "meter" in t or "sensor" in t:
        return "temp_humidity"
    return t or "switchbot"


def _infer_switchbot_caps(payload: dict) -> list[str]:
    caps: list[str] = []
    dtype = (payload.get("device_type") or payload.get("domain") or "").lower()
    if "plug" in dtype or "switch" in dtype or "bulb" in dtype or "light" in dtype:
        caps.append("on_off")
    if "bulb" in dtype or "strip" in dtype:
        caps.extend(["brightness", "color_temp"])
    if "curtain" in dtype or "blind" in dtype:
        caps.append("set_position")
    if "hub" in dtype:
        caps.append("ir_send")
    if "plug" in dtype:
        caps.append("pulse")
    return caps


def _extract_state(payload: dict) -> dict[str, Any]:
    state = {}
    if "state" in payload:
        raw = payload["state"]
        if isinstance(raw, str):
            state["on"] = raw.lower() in ("on", "open", "true", "1")
        else:
            state["on"] = bool(raw)
    for k in ("brightness", "color_temp", "position", "power_state"):
        if k in payload:
            state[k] = payload[k]
    return state


class SwitchBotParser(VendorParser):
    vendor = "switchbot"

    def matches(self, parts: list[str]) -> bool:
        # hems/switchbot/{device_id}/state
        return (
            len(parts) >= 3
            and parts[0] == "hems"
            and parts[1] == "switchbot"
            and len(parts) >= 4
            and parts[3] == "state"
        )

    def parse(self, parts: list[str], payload: dict) -> DeviceObservation | None:
        vendor_ref = parts[2]
        device_id = f"switchbot.{vendor_ref}"
        return DeviceObservation(
            device_id=device_id,
            vendor="switchbot",
            vendor_ref=vendor_ref,
            kind="both",
            device_class=_infer_switchbot_class(payload),
            capabilities=_infer_switchbot_caps(payload),
            zone=payload.get("zone"),
            last_state=_extract_state(payload),
            last_value=_extract_sensor_values(payload),
            battery_pct=payload.get("battery"),
            link_quality=payload.get("rssi") if isinstance(payload.get("rssi"), (int, float)) else None,
        )

    async def dispatch(self, ctx: DispatchContext, device: dict, action: str, params: dict) -> dict[str, Any]:
        if not ctx.switchbot_url:
            return {"success": False, "error": "SwitchBot bridge not configured"}
        # W1.2: guard before injecting device_ref into HTTP URL path
        device_ref, err = DispatchContext.resolve_ref(device, "switchbot")
        if err is not None:
            return err

        cmd, parameter, cmd_type = _switchbot_cmd_for(action, params)
        if cmd is None:
            return {"success": False, "error": f"action '{action}' not mapped for SwitchBot"}

        async with ctx.session.post(
            f"{ctx.switchbot_url}/api/devices/{device_ref}/command",
            json={"command": cmd, "parameter": parameter, "command_type": cmd_type},
            headers=internal_headers(),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()
            if resp.status == 200:
                return {"success": True, "result": f"switchbot {cmd} -> {device_ref}"}
            return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
