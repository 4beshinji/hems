import json
from typing import Any

import aiohttp


class PCToolHandlers:
    async def _handle_get_pc_status(self, args: dict[str, Any]) -> dict[str, Any]:
        pc = self.world_model.pc_state
        status = {
            "cpu_percent": pc.cpu.usage_percent,
            "cpu_cores": pc.cpu.core_count,
            "memory_percent": pc.memory.percent,
            "memory_used_gb": pc.memory.used_gb,
            "memory_total_gb": pc.memory.total_gb,
            "gpu_percent": pc.gpu.usage_percent,
            "gpu_vram_used_gb": pc.gpu.vram_used_gb,
            "gpu_vram_total_gb": pc.gpu.vram_total_gb,
            "bridge_connected": pc.bridge_connected,
        }
        if pc.cpu.temp_c > 0:
            status["cpu_temp_c"] = pc.cpu.temp_c
        if pc.gpu.temp_c > 0:
            status["gpu_temp_c"] = pc.gpu.temp_c
        if pc.disk.partitions:
            status["disk"] = [
                {"mount": p.mount, "percent": p.percent, "used_gb": p.used_gb, "total_gb": p.total_gb}
                for p in pc.disk.partitions
            ]
        if args.get("include_processes") and pc.top_processes:
            status["processes"] = [
                {"pid": p.pid, "name": p.name, "cpu": p.cpu_percent, "mem_mb": p.mem_mb} for p in pc.top_processes[:10]
            ]
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    async def _handle_run_pc_command(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.openclaw_url:
            return {"success": False, "error": "OpenClaw bridge not configured"}
        try:
            async with self._session.post(
                f"{self.openclaw_url}/api/pc/command",
                json={
                    "command": args.get("command", ""),
                    "cwd": args.get("cwd"),
                    "timeout": args.get("timeout", 30),
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data.get("result", {}), ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_control_browser(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.openclaw_url:
            return {"success": False, "error": "OpenClaw bridge not configured"}
        action = args.get("action", "")
        endpoint_map = {
            "navigate": ("/api/pc/browser/navigate", {"url": args.get("url", "")}),
            "eval": ("/api/pc/browser/eval", {"javascript": args.get("javascript", "")}),
            "get_url": ("/api/pc/browser/get_url", {}),
            "get_title": ("/api/pc/browser/get_title", {}),
        }
        if action not in endpoint_map:
            return {"success": False, "error": f"Unknown browser action: {action}"}
        path, body = endpoint_map[action]
        try:
            async with self._session.post(
                f"{self.openclaw_url}{path}",
                json=body,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data.get("result", {}), ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_send_pc_notification(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.openclaw_url:
            return {"success": False, "error": "OpenClaw bridge not configured"}
        try:
            async with self._session.post(
                f"{self.openclaw_url}/api/pc/notify",
                json={
                    "title": args.get("title", ""),
                    "body": args.get("body", ""),
                    "priority": args.get("priority", "active"),
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": "Notification sent"}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_list_processes(self, args: dict[str, Any]) -> dict[str, Any]:
        """List PC processes from world_model.pc_state.top_processes with filtering/sorting."""
        pc = self.world_model.pc_state
        procs = pc.top_processes or []
        if not procs:
            return {"success": True, "result": "プロセス情報がありません"}

        sort_by = args.get("sort_by", "cpu")
        name_filter = (args.get("name_contains") or "").lower()
        limit = max(1, min(int(args.get("limit", 10)), 50))

        filtered = [p for p in procs if not name_filter or name_filter in p.name.lower()]
        if sort_by == "memory":
            filtered.sort(key=lambda p: p.mem_mb, reverse=True)
        else:
            filtered.sort(key=lambda p: p.cpu_percent, reverse=True)

        result = [
            {
                "pid": p.pid,
                "name": p.name,
                "cpu_percent": round(p.cpu_percent, 1),
                "mem_mb": round(p.mem_mb, 1),
            }
            for p in filtered[:limit]
        ]
        return {
            "success": True,
            "result": json.dumps({"processes": result, "total": len(filtered)}, ensure_ascii=False),
        }
