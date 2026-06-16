import asyncio
import json
from typing import Any

import aiohttp

from tool_http import internal_headers


class HomeToolHandlers:
    async def _handle_control_light(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.ha_url:
            return {"success": False, "error": "HA bridge not configured"}
        entity_id = args.get("entity_id", "")
        on = args.get("on", True)
        service = "light/turn_on" if on else "light/turn_off"
        data = {}
        if on and args.get("brightness") is not None:
            data["brightness"] = args["brightness"]
        if on and args.get("color_temp") is not None:
            data["color_temp"] = args["color_temp"]
        return await self._ha_service_call(entity_id, service, data)

    async def _handle_control_climate(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.ha_url:
            return {"success": False, "error": "HA bridge not configured"}
        entity_id = args.get("entity_id", "")
        mode = args.get("mode")
        if mode == "off":
            return await self._ha_service_call(entity_id, "climate/turn_off")

        data = {}
        if mode:
            data["hvac_mode"] = mode
        if args.get("temperature") is not None:
            data["temperature"] = args["temperature"]
        if args.get("fan_mode"):
            data["fan_mode"] = args["fan_mode"]
        service = "climate/set_hvac_mode" if mode and not data.get("temperature") else "climate/set_temperature"
        if mode and data.get("temperature"):
            await self._ha_service_call(entity_id, "climate/set_hvac_mode", {"hvac_mode": mode})
            return await self._ha_service_call(
                entity_id,
                "climate/set_temperature",
                {
                    "temperature": data["temperature"],
                    **({"fan_mode": data["fan_mode"]} if "fan_mode" in data else {}),
                },
            )
        return await self._ha_service_call(entity_id, service, data)

    async def _handle_control_cover(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.ha_url:
            return {"success": False, "error": "HA bridge not configured"}
        entity_id = args.get("entity_id", "")
        action = args.get("action")
        position = args.get("position")

        if position is not None:
            return await self._ha_service_call(entity_id, "cover/set_cover_position", {"position": position})
        if action == "open":
            return await self._ha_service_call(entity_id, "cover/open_cover")
        elif action == "close":
            return await self._ha_service_call(entity_id, "cover/close_cover")
        elif action == "stop":
            return await self._ha_service_call(entity_id, "cover/stop_cover")
        return {"success": False, "error": "No action or position specified"}

    async def _handle_control_switch(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.ha_url:
            return {"success": False, "error": "HA bridge not configured"}
        entity_id = args.get("entity_id", "")
        on = args.get("on", True)
        service = "switch/turn_on" if on else "switch/turn_off"
        return await self._ha_service_call(entity_id, service)

    async def _handle_get_sensor_data(self, args: dict[str, Any]) -> dict[str, Any]:
        hd = self.world_model.home_devices
        entity_id = args.get("entity_id")
        device_class = args.get("device_class")

        if entity_id:
            s = hd.sensors.get(entity_id)
            if not s:
                return {"success": False, "error": f"Sensor '{entity_id}' not found"}
            data = {"entity_id": s.entity_id, "value": s.value, "unit": s.unit, "device_class": s.device_class}
            return {"success": True, "result": json.dumps(data, ensure_ascii=False)}

        sensors = hd.sensors.values()
        if device_class:
            sensors = [s for s in sensors if s.device_class == device_class]
        data = {s.entity_id: {"value": s.value, "unit": s.unit, "device_class": s.device_class} for s in sensors}
        return {"success": True, "result": json.dumps(data, ensure_ascii=False)}

    async def _handle_execute_scene(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.ha_url:
            return {"success": False, "error": "HA bridge not configured"}
        entity_id = args.get("entity_id", "")
        return await self._ha_service_call(entity_id, "scene/turn_on")

    async def _handle_get_home_devices(self, args: dict[str, Any]) -> dict[str, Any]:
        hd = self.world_model.home_devices
        status = {
            "bridge_connected": hd.bridge_connected,
            "lights": {eid: {"on": lt.on, "brightness": lt.brightness} for eid, lt in hd.lights.items()},
            "climates": {
                eid: {"mode": c.mode, "target_temp": c.target_temp, "current_temp": c.current_temp}
                for eid, c in hd.climates.items()
            },
            "covers": {eid: {"position": c.position, "is_open": c.is_open} for eid, c in hd.covers.items()},
            "switches": hd.switches,
            "binary_sensors": {
                eid: {"state": bs.state, "device_class": bs.device_class} for eid, bs in hd.binary_sensors.items()
            },
            "sensors": {
                eid: {"value": s.value, "unit": s.unit, "device_class": s.device_class} for eid, s in hd.sensors.items()
            },
        }
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    async def _handle_get_entity_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get a single HA entity's current state via ha-bridge."""
        if not self.ha_url:
            return {"success": False, "error": "HA bridge not configured"}
        entity_id = args.get("entity_id", "").strip()
        if not entity_id:
            return {"success": False, "error": "entity_id required"}
        try:
            async with self._session.get(
                f"{self.ha_url}/api/device/{entity_id}",
                headers=internal_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                if resp.status == 404:
                    return {"success": False, "error": f"Entity not found: {entity_id}"}
                return {"success": False, "error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_power_consumption(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get instant power (W) for a Tapo plug, or all plugs if device_id omitted."""
        if not self.tapo_url:
            return {"success": False, "error": "Tapo bridge not configured"}
        device_id = (args.get("device_id") or "").strip()
        try:
            if device_id:
                vendor_ref = device_id.removeprefix("tapo.")
                async with self._session.get(
                    f"{self.tapo_url}/api/devices/{vendor_ref}/status",
                    headers=internal_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return {"success": True, "result": json.dumps(await resp.json(), ensure_ascii=False)}
                    return {"success": False, "error": f"HTTP {resp.status}"}
            async with self._session.get(
                f"{self.tapo_url}/api/devices",
                headers=internal_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return {"success": False, "error": f"HTTP {resp.status}"}
                data = await resp.json()

            devices = [d for d in data.get("devices", []) if d.get("vendor_ref")]

            async def _fetch(d: dict) -> dict | None:
                vref = d["vendor_ref"]
                try:
                    async with self._session.get(
                        f"{self.tapo_url}/api/devices/{vref}/status",
                        headers=internal_headers(),
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as r2:
                        if r2.status != 200:
                            return None
                        s = await r2.json()
                except Exception:
                    return None
                return {
                    "device_id": f"tapo.{vref}",
                    "name": d.get("name"),
                    "zone": d.get("zone"),
                    "power_watts": s.get("power_watts"),
                    "voltage": s.get("voltage"),
                    "current": s.get("current"),
                    "energy_kwh": s.get("energy_kwh"),
                    "on": s.get("state") == "on" or s.get("on") is True,
                }

            gathered = await asyncio.gather(*(_fetch(d) for d in devices), return_exceptions=False)
            results = [r for r in gathered if r is not None]
            return {"success": True, "result": json.dumps({"devices": results}, ensure_ascii=False)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _ha_service_call(self, entity_id: str, service: str, data: dict = None) -> dict[str, Any]:
        """Call HA bridge REST API to execute a service call."""
        try:
            async with self._session.post(
                f"{self.ha_url}/api/device/control",
                json={
                    "entity_id": entity_id,
                    "service": service,
                    "data": data or {},
                },
                headers=internal_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                result = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": f"{service} -> {entity_id}"}
                return {"success": False, "error": result.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}
