from typing import Any

import aiohttp


class SwitchBotToolHandlers:
    async def _handle_get_switchbot_devices(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get SwitchBot device list from bridge."""
        if not self.switchbot_url:
            return {"success": False, "error": "SwitchBot bridge not configured"}
        try:
            async with self._session.get(
                f"{self.switchbot_url}/api/devices",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    devices = data.get("devices", [])
                    ir_devices = data.get("ir_devices", [])
                    lines = []
                    for d in devices:
                        name = d.get("device_name", "")
                        dtype = d.get("device_type", "")
                        zone = d.get("zone", "")
                        did = d.get("device_id", "")
                        lines.append(f"- {name} ({dtype}) [{zone}] ID:{did}")
                    for d in ir_devices:
                        name = d.get("device_name", "")
                        rtype = d.get("remote_type", "")
                        did = d.get("device_id", "")
                        lines.append(f"- {name} (IR:{rtype}) ID:{did}")
                    summary = f"SwitchBotデバイス ({len(devices)}台 + IR {len(ir_devices)}台):\n"
                    summary += "\n".join(lines) if lines else "デバイスなし"
                    return {"success": True, "result": summary}
                return {"success": False, "error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_control_switchbot(self, args: dict[str, Any]) -> dict[str, Any]:
        """Send command to a SwitchBot device via bridge."""
        if not self.switchbot_url:
            return {"success": False, "error": "SwitchBot bridge not configured"}
        device_id = args.get("device_id", "")
        command = args.get("command", "")
        parameter = args.get("parameter", "default")
        try:
            async with self._session.post(
                f"{self.switchbot_url}/api/devices/{device_id}/command",
                json={
                    "command": command,
                    "parameter": parameter,
                    "command_type": "command",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": f"SwitchBot {command} -> {device_id}"}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_send_switchbot_ir(self, args: dict[str, Any]) -> dict[str, Any]:
        """Send IR command via SwitchBot Hub."""
        if not self.switchbot_url:
            return {"success": False, "error": "SwitchBot bridge not configured"}
        device_id = args.get("device_id", "")
        command = args.get("command", "")
        parameter = args.get("parameter", "default")
        try:
            async with self._session.post(
                f"{self.switchbot_url}/api/devices/{device_id}/command",
                json={
                    "command": command,
                    "parameter": parameter,
                    "command_type": "customize",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": f"SwitchBot IR {command} -> {device_id}"}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}
