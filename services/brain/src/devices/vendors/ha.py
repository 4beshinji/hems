"""Home Assistant vendor parser + dispatch."""

from __future__ import annotations

from typing import Any

import aiohttp

from devices.actions import _ha_service_for
from devices.base import DispatchContext, VendorParser
from devices.observation import DeviceObservation, _extract_sensor_values
from tool_http import internal_headers


def _infer_ha_kind(domain: str) -> str:
    if domain in ("sensor", "binary_sensor"):
        return "sensor"
    if domain in ("light", "switch", "climate", "cover", "scene"):
        return "actuator"
    return "both"


def _infer_ha_class(domain: str, payload: dict) -> str:
    if domain == "light":
        return "light"
    if domain == "switch":
        return "plug"
    if domain == "climate":
        return "climate"
    if domain == "cover":
        return "curtain"
    device_class = payload.get("device_class")
    if device_class:
        return str(device_class)
    return domain


def _infer_ha_caps(domain: str, payload: dict) -> list[str]:
    caps: list[str] = []
    if domain == "light":
        caps.append("on_off")
        if "brightness" in payload:
            caps.append("brightness")
        if "color_temp" in payload:
            caps.append("color_temp")
    elif domain == "switch":
        caps.extend(["on_off", "pulse"])
    elif domain == "cover":
        caps.append("set_position")
    elif domain == "climate":
        caps.append("set_temperature")
    return caps


def _extract_ha_state(domain: str, payload: dict) -> dict[str, Any]:
    state = {}
    raw = payload.get("state")
    if raw is not None:
        if domain == "cover":
            state["position"] = payload.get("current_position", 100 if raw == "open" else 0)
        else:
            state["on"] = str(raw).lower() in ("on", "open", "true", "1", "home")
    for k in ("brightness", "color_temp", "current_position", "current_temperature", "hvac_mode"):
        if k in payload:
            state[k] = payload[k]
    return state


class HAParser(VendorParser):
    vendor = "ha"

    def matches(self, parts: list[str]) -> bool:
        # hems/home/{zone}/{domain}/{entity_id}/state
        return len(parts) >= 6 and parts[0] == "hems" and parts[1] == "home" and parts[5] == "state"

    def parse(self, parts: list[str], payload: dict) -> DeviceObservation | None:
        zone_id, domain, entity_id = parts[2], parts[3], parts[4]
        # entity_id sometimes contains dots already; the ha-bridge flattens them
        ha_entity = payload.get("entity_id", f"{domain}.{entity_id}")
        device_id = f"ha.{ha_entity}"
        return DeviceObservation(
            device_id=device_id,
            vendor="ha",
            vendor_ref=ha_entity,
            kind=_infer_ha_kind(domain),
            device_class=_infer_ha_class(domain, payload),
            capabilities=_infer_ha_caps(domain, payload),
            zone=zone_id,
            last_state=_extract_ha_state(domain, payload),
            last_value=_extract_sensor_values(payload),
        )

    async def dispatch(self, ctx: DispatchContext, device: dict, action: str, params: dict) -> dict[str, Any]:
        if not ctx.ha_url:
            return {"success": False, "error": "HA bridge not configured"}
        entity_id = device.get("vendor_ref") or device.get("device_id", "").replace("ha.", "")
        domain = entity_id.split(".")[0] if "." in entity_id else ""

        # rainbow: async hue cycling via repeated HA calls
        if action == "rainbow":
            duration = int(params.get("duration_s", 10))
            if duration > 60:
                return {"success": False, "error": "rainbow duration_s > 60 rejected"}
            ctx.asyncio.ensure_future(self._ha_rainbow(ctx, entity_id, duration))
            return {"success": True, "result": f"ha rainbow {duration}s -> {entity_id}"}

        service, data = _ha_service_for(action, params, domain)
        if service is None:
            return {"success": False, "error": f"action '{action}' not mapped for HA domain '{domain}'"}

        async with ctx.session.post(
            f"{ctx.ha_url}/api/device/control",
            json={"entity_id": entity_id, "service": service, "data": data or {}},
            headers=internal_headers(),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            result = await resp.json()
            if resp.status == 200:
                return {"success": True, "result": f"ha {action} -> {entity_id}"}
            return {"success": False, "error": result.get("detail", f"HTTP {resp.status}")}

    async def _ha_rainbow(self, ctx: DispatchContext, entity_id: str, duration: int):
        """Cycle through rainbow hues via HA light/turn_on calls."""
        steps = min(duration * 2, 20)
        interval = duration / steps
        for i in range(steps):
            hue = 360.0 * i / steps
            try:
                async with ctx.session.post(
                    f"{ctx.ha_url}/api/device/control",
                    json={
                        "entity_id": entity_id,
                        "service": "light/turn_on",
                        "data": {"hs_color": [hue, 100], "brightness": 254},
                    },
                    headers=internal_headers(),
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    await resp.read()
            except Exception:
                pass
            await ctx.asyncio.sleep(interval)
        # Restore warm white
        try:
            async with ctx.session.post(
                f"{ctx.ha_url}/api/device/control",
                json={"entity_id": entity_id, "service": "light/turn_on", "data": {"color_temp": 350}},
                headers=internal_headers(),
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                await resp.read()
        except Exception:
            pass
