"""
Tool executor — routes tool calls through sanitizer to handlers.
Forked from SOMS: removed wallet integration. Extended with PC tools.
"""
import json
import os
from loguru import logger

OPENCLAW_BRIDGE_URL = os.getenv("OPENCLAW_BRIDGE_URL", "")
OBSIDIAN_BRIDGE_URL = os.getenv("OBSIDIAN_BRIDGE_URL", "")


class ToolExecutor:
    def __init__(self, sanitizer, mcp_bridge, dashboard_client, world_model,
                 task_queue, session, device_registry):
        self.sanitizer = sanitizer
        self.mcp = mcp_bridge
        self.dashboard = dashboard_client
        self.world_model = world_model
        self.task_queue = task_queue
        self.session = session
        self.device_registry = device_registry
        self.openclaw_url = OPENCLAW_BRIDGE_URL
        self.obsidian_url = OBSIDIAN_BRIDGE_URL

    async def execute(self, tool_name: str, arguments: dict) -> dict:
        """Execute a tool call with sanitizer validation."""
        # Validate through sanitizer
        validation = self.sanitizer.validate_tool_call(tool_name, arguments)
        if not validation["allowed"]:
            return {"success": False, "error": validation["reason"]}

        try:
            if tool_name == "create_task":
                return await self._handle_create_task(arguments)
            elif tool_name == "send_device_command":
                return await self._handle_device_command(arguments)
            elif tool_name == "get_zone_status":
                return await self._handle_get_zone_status(arguments)
            elif tool_name == "speak":
                return await self._handle_speak(arguments)
            elif tool_name == "get_pc_status":
                return await self._handle_get_pc_status(arguments)
            elif tool_name == "run_pc_command":
                return await self._handle_run_pc_command(arguments)
            elif tool_name == "control_browser":
                return await self._handle_control_browser(arguments)
            elif tool_name == "send_pc_notification":
                return await self._handle_send_pc_notification(arguments)
            elif tool_name == "get_service_status":
                return await self._handle_get_service_status(arguments)
            elif tool_name == "search_notes":
                return await self._handle_search_notes(arguments)
            elif tool_name == "write_note":
                return await self._handle_write_note(arguments)
            elif tool_name == "get_recent_notes":
                return await self._handle_get_recent_notes(arguments)
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {"success": False, "error": str(e)}

    async def _handle_create_task(self, args: dict) -> dict:
        result = await self.dashboard.create_task(args)
        if result:
            return {"success": True, "result": f"Task created: {result.get('title', '')} (id={result.get('id', '')})"}
        return {"success": False, "error": "Failed to create task"}

    async def _handle_device_command(self, args: dict) -> dict:
        agent_id = args.get("agent_id", "")
        tool_name = args.get("tool_name", "")
        tool_args = args.get("arguments", {})

        result = await self.mcp.call_tool(agent_id, tool_name, tool_args)
        if result is not None:
            return {"success": True, "result": json.dumps(result, ensure_ascii=False)}
        return {"success": False, "error": f"MCP call to {agent_id}/{tool_name} failed or timed out"}

    async def _handle_get_zone_status(self, args: dict) -> dict:
        zone_id = args.get("zone_id", "")
        zone = self.world_model.zones.get(zone_id)
        if not zone:
            return {"success": False, "error": f"Zone '{zone_id}' not found"}

        env = zone.environment
        status = {
            "zone_id": zone_id,
            "temperature": env.temperature,
            "humidity": env.humidity,
            "co2": env.co2,
            "occupancy_count": zone.occupancy.count if zone.occupancy else 0,
            "recent_events": [
                {"type": e.event_type, "description": e.description, "severity": e.severity}
                for e in zone.events[-5:]
            ],
        }
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    async def _handle_speak(self, args: dict) -> dict:
        message = args.get("message", "")
        zone = args.get("zone", "")
        tone = args.get("tone", "neutral")

        result = await self.dashboard.speak(message, zone, tone)
        if result:
            return {"success": True, "result": f"Spoke: {message[:50]}"}
        return {"success": False, "error": "Speak failed"}

    # --- PC tools (OpenClaw) ---

    async def _handle_get_pc_status(self, args: dict) -> dict:
        pc = self.world_model.pc_state
        status = {
            "cpu_percent": pc.cpu.usage_percent,
            "cpu_cores": pc.cpu.core_count,
            "cpu_temp_c": pc.cpu.temp_c,
            "memory_percent": pc.memory.percent,
            "memory_used_gb": pc.memory.used_gb,
            "memory_total_gb": pc.memory.total_gb,
            "gpu_percent": pc.gpu.usage_percent,
            "gpu_temp_c": pc.gpu.temp_c,
            "gpu_vram_used_gb": pc.gpu.vram_used_gb,
            "gpu_vram_total_gb": pc.gpu.vram_total_gb,
            "bridge_connected": pc.bridge_connected,
        }
        if pc.disk.partitions:
            status["disk"] = [
                {"mount": p.mount, "percent": p.percent, "used_gb": p.used_gb, "total_gb": p.total_gb}
                for p in pc.disk.partitions
            ]
        if args.get("include_processes") and pc.top_processes:
            status["processes"] = [
                {"pid": p.pid, "name": p.name, "cpu": p.cpu_percent, "mem_mb": p.mem_mb}
                for p in pc.top_processes[:10]
            ]
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    async def _handle_run_pc_command(self, args: dict) -> dict:
        if not self.openclaw_url:
            return {"success": False, "error": "OpenClaw bridge not configured"}
        try:
            async with self.session.post(
                f"{self.openclaw_url}/api/pc/command",
                json={
                    "command": args.get("command", ""),
                    "cwd": args.get("cwd"),
                    "timeout": args.get("timeout", 30),
                },
                timeout=60,
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data.get("result", {}), ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_control_browser(self, args: dict) -> dict:
        if not self.openclaw_url:
            return {"success": False, "error": "OpenClaw bridge not configured"}
        action = args.get("action", "")
        endpoint_map = {
            "navigate": ("/api/pc/browser/navigate", {"url": args.get("url", "")}),
            "eval": ("/api/pc/browser/eval", {"javascript": args.get("javascript", "")}),
            "get_url": ("/api/pc/browser/get_url", None),
            "get_title": ("/api/pc/browser/get_title", None),
        }
        if action not in endpoint_map:
            return {"success": False, "error": f"Unknown browser action: {action}"}
        path, body = endpoint_map[action]
        try:
            method = self.session.post if body is not None else self.session.post
            async with method(
                f"{self.openclaw_url}{path}",
                json=body or {},
                timeout=15,
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data.get("result", {}), ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Service tools ---

    async def _handle_get_service_status(self, args: dict) -> dict:
        ss = self.world_model.services_state
        service_name = args.get("service_name")
        if service_name:
            svc = ss.services.get(service_name)
            if not svc:
                return {"success": False, "error": f"Service '{service_name}' not found"}
            status = {
                "name": svc.name, "available": svc.available,
                "unread_count": svc.unread_count, "summary": svc.summary,
                "last_check": svc.last_check, "error": svc.error,
            }
        else:
            status = {
                name: {
                    "name": svc.name, "available": svc.available,
                    "unread_count": svc.unread_count, "summary": svc.summary,
                    "last_check": svc.last_check, "error": svc.error,
                }
                for name, svc in ss.services.items()
            }
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    async def _handle_send_pc_notification(self, args: dict) -> dict:
        if not self.openclaw_url:
            return {"success": False, "error": "OpenClaw bridge not configured"}
        try:
            async with self.session.post(
                f"{self.openclaw_url}/api/pc/notify",
                json={
                    "title": args.get("title", ""),
                    "body": args.get("body", ""),
                    "priority": args.get("priority", "active"),
                },
                timeout=10,
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": "Notification sent"}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Obsidian tools ---

    async def _handle_search_notes(self, args: dict) -> dict:
        if not self.obsidian_url:
            return {"success": False, "error": "Obsidian bridge not configured"}
        try:
            async with self.session.post(
                f"{self.obsidian_url}/api/notes/search",
                json={
                    "query": args.get("query", ""),
                    "tags": args.get("tags"),
                    "path_prefix": args.get("path_prefix"),
                    "max_results": args.get("max_results", 5),
                },
                timeout=10,
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_write_note(self, args: dict) -> dict:
        if not self.obsidian_url:
            return {"success": False, "error": "Obsidian bridge not configured"}
        try:
            async with self.session.post(
                f"{self.obsidian_url}/api/notes/write",
                json={
                    "title": args.get("title", ""),
                    "content": args.get("content", ""),
                    "tags": args.get("tags"),
                    "category": args.get("category"),
                },
                timeout=10,
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_recent_notes(self, args: dict) -> dict:
        if not self.obsidian_url:
            return {"success": False, "error": "Obsidian bridge not configured"}
        try:
            async with self.session.get(
                f"{self.obsidian_url}/api/notes/recent",
                params={"limit": args.get("limit", 5)},
                timeout=10,
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}
