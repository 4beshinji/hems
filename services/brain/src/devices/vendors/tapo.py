"""Tapo (P110/P115) vendor parser + dispatch."""

from __future__ import annotations

from typing import Any

import aiohttp

from devices.base import DispatchContext, VendorParser
from devices.observation import DeviceObservation


class TapoParser(VendorParser):
    vendor = "tapo"

    def matches(self, parts: list[str]) -> bool:
        # hems/tapo/{device_id}/state
        return len(parts) >= 4 and parts[0] == "hems" and parts[1] == "tapo" and parts[3] == "state"

    def parse(self, parts: list[str], payload: dict) -> DeviceObservation | None:
        vendor_ref = parts[2]
        device_id = f"tapo.{vendor_ref}"
        return DeviceObservation(
            device_id=device_id,
            vendor="tapo",
            vendor_ref=vendor_ref,
            kind="both",
            device_class="plug",
            capabilities=["on_off", "pulse"],
            zone=payload.get("zone"),
            last_state={"on": payload.get("state") == "on" or bool(payload.get("on"))},
            last_value={k: payload[k] for k in ("power_watts", "voltage", "current", "energy_kwh") if k in payload},
        )

    async def dispatch(self, ctx: DispatchContext, device: dict, action: str, params: dict) -> dict[str, Any]:
        if not ctx.tapo_url:
            return {"success": False, "error": "Tapo bridge not configured"}
        # W1.2: guard before injecting device_ref into HTTP URL path
        device_ref, err = DispatchContext.resolve_ref(device, "tapo")
        if err is not None:
            return err

        # pulse is handled here: on → sleep → off
        if action == "pulse":
            duration = int(params.get("duration_s", 10))
            if duration > 600:
                return {"success": False, "error": "pulse duration_s > 600 rejected"}
            r1 = await self._tapo_raw(ctx, device_ref, "turnOn")
            if not r1.get("success"):
                return r1
            await ctx.asyncio.sleep(duration)
            r2 = await self._tapo_raw(ctx, device_ref, "turnOff")
            if not r2.get("success"):
                return {"success": False, "error": f"pulse on ok but off failed: {r2.get('error')}"}
            return {"success": True, "result": f"tapo pulse {duration}s -> {device_ref}"}

        cmd = {"on": "turnOn", "off": "turnOff", "toggle": "toggle"}.get(action)
        if not cmd:
            return {"success": False, "error": f"action '{action}' not supported by Tapo"}
        return await self._tapo_raw(ctx, device_ref, cmd)

    async def _tapo_raw(self, ctx: DispatchContext, device_ref: str, command: str) -> dict[str, Any]:
        try:
            async with ctx.session.post(
                f"{ctx.tapo_url}/api/devices/{device_ref}/command",
                json={"command": command},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": f"tapo {command} -> {device_ref}"}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}
