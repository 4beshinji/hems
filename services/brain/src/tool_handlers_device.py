import asyncio
import json
from typing import Any


class DeviceToolHandlers:
    async def _handle_control_actuator(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.device_dispatcher is None:
            return {"success": False, "error": "Device dispatcher not configured"}
        device_id = args.get("device_id", "")
        action = args.get("action", "")
        params = args.get("params") or {}
        if not device_id or not action:
            return {"success": False, "error": "device_id and action are required"}
        result = await self.device_dispatcher.dispatch(device_id, action, params)
        try:
            asyncio.create_task(
                self.dashboard.push_device_action(
                    device_id=device_id,
                    action=action,
                    params=params,
                    source=args.get("_source", "llm"),
                    success=bool(result.get("success", False)),
                )
            )
        except Exception:
            pass
        return result

    async def _handle_list_devices(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.device_dispatcher is None:
            return {"success": False, "error": "Device dispatcher not configured"}
        devices = await self.device_dispatcher.list_all(
            kind=args.get("kind"),
            zone=args.get("zone"),
            vendor=args.get("vendor"),
        )

        capability = args.get("capability")
        purpose_sub = args.get("purpose_contains")

        def _match(d: dict) -> bool:
            if capability and capability not in (d.get("capabilities") or []):
                return False
            if purpose_sub and purpose_sub not in (d.get("purpose") or ""):
                return False
            return True

        filtered = [d for d in devices if _match(d)]
        summary = [
            {
                "device_id": d["device_id"],
                "kind": d.get("kind"),
                "vendor": d.get("vendor"),
                "device_class": d.get("device_class"),
                "capabilities": d.get("capabilities", []),
                "channels": d.get("channels", []),
                "zone": d.get("zone"),
                "location": d.get("location"),
                "purpose": d.get("purpose"),
                "display_name": d.get("display_name"),
                "is_enabled": d.get("is_enabled", True),
                "last_state": d.get("last_state") or {},
                "last_value": d.get("last_value") or {},
            }
            for d in filtered
        ]
        return {"success": True, "result": json.dumps(summary, ensure_ascii=False)}

    async def _handle_describe_device(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.device_dispatcher is None:
            return {"success": False, "error": "Device dispatcher not configured"}
        device_id = args.get("device_id", "")
        if not device_id:
            return {"success": False, "error": "device_id is required"}
        device = await self.device_dispatcher.lookup(device_id)
        if device is None:
            return {"success": False, "error": f"Device '{device_id}' not found"}
        return {"success": True, "result": json.dumps(device, ensure_ascii=False)}

    async def _handle_zigbee_permit_join(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.device_dispatcher is None:
            return {"success": False, "error": "Device dispatcher not configured"}
        enable = bool(args.get("enable", False))
        duration_s = int(args.get("duration_s", 60) or 0)
        return self.device_dispatcher.zigbee_permit_join(enable, duration_s)

    async def _handle_execute_scene_by_name(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.scene_executor is None:
            return {"success": False, "error": "Scene executor not configured"}
        name = args.get("name", "")
        if not name:
            return {"success": False, "error": "name is required"}
        result = await self.scene_executor.execute_by_name(name)
        if result.get("success"):
            return {"success": True, "result": f"scene '{name}': {result['executed']} actions executed"}
        return {"success": False, "error": f"scene '{name}' failed: {'; '.join(result.get('errors', []))}"}

    async def _handle_list_scenes(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.scene_executor is None:
            return {"success": False, "error": "Scene executor not configured"}
        scenes = await self.scene_executor.list_scenes()
        summary = [
            {
                "name": s.get("name"),
                "display_name": s.get("display_name"),
                "description": s.get("description"),
                "action_count": len(s.get("actions") or []),
                "is_enabled": s.get("is_enabled", True),
            }
            for s in scenes
        ]
        return {"success": True, "result": json.dumps(summary, ensure_ascii=False)}
