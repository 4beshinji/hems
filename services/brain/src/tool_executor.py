"""
Tool executor — routes tool calls through sanitizer to handlers.
Forked from SOMS: extended with PC tools (OpenClaw), Obsidian tools, and
adaptive device timeout + queued response handling.
"""
import json
import os
from typing import Dict, Any
import aiohttp
from loguru import logger

LOCALCRAW_BRIDGE_URL = os.getenv("LOCALCRAW_BRIDGE_URL", "")
OBSIDIAN_BRIDGE_URL = os.getenv("OBSIDIAN_BRIDGE_URL", "")
HA_BRIDGE_URL = os.getenv("HA_BRIDGE_URL", "")
BIOMETRIC_BRIDGE_URL = os.getenv("BIOMETRIC_BRIDGE_URL", "")


class ToolExecutor:
    def __init__(self, sanitizer, mcp_bridge, dashboard_client, world_model,
                 task_queue, session: aiohttp.ClientSession = None, device_registry=None):
        self.sanitizer = sanitizer
        self.mcp = mcp_bridge
        self.dashboard = dashboard_client
        self.world_model = world_model
        self.task_queue = task_queue
        self._session = session
        self.device_registry = device_registry
        self.openclaw_url = LOCALCRAW_BRIDGE_URL
        self.obsidian_url = OBSIDIAN_BRIDGE_URL
        self.ha_url = HA_BRIDGE_URL
        self.biometric_url = BIOMETRIC_BRIDGE_URL
        self.voice_url = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")
        self.dashboard_api_url = os.getenv("DASHBOARD_API_URL", "http://backend:8000")

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool call with sanitizer validation.

        Returns:
            {"success": True, "result": "..."} or {"success": False, "error": "..."}
        """
        # Validate through sanitizer (dict return: {"allowed": bool, "reason": str})
        validation = self.sanitizer.validate_tool_call(tool_name, arguments)
        if not validation["allowed"]:
            logger.warning(f"Tool call REJECTED: {tool_name} - {validation['reason']}")
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
            elif tool_name == "get_active_tasks":
                return await self._handle_get_active_tasks()
            elif tool_name == "get_device_status":
                return await self._handle_get_device_status(arguments)
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
            elif tool_name == "control_light":
                return await self._handle_control_light(arguments)
            elif tool_name == "control_climate":
                return await self._handle_control_climate(arguments)
            elif tool_name == "control_cover":
                return await self._handle_control_cover(arguments)
            elif tool_name == "get_home_devices":
                return await self._handle_get_home_devices(arguments)
            elif tool_name == "get_biometrics":
                return await self._handle_get_biometrics(arguments)
            elif tool_name == "get_sleep_summary":
                return await self._handle_get_sleep_summary(arguments)
            elif tool_name == "get_perception_status":
                return await self._handle_get_perception_status(arguments)
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {"success": False, "error": str(e)}

    async def _handle_create_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a task via DashboardClient and register with TaskQueueManager."""
        title = args.get("title", "")
        xp_reward = args.get("xp_reward", 100)
        urgency = args.get("urgency", 2)
        zone = args.get("zone")

        result = await self.dashboard.create_task(args)

        if result and result.get("id"):
            task_id = result["id"]

            # Record successful creation for rate limiting
            self.sanitizer.record_task_created()

            # Register with TaskQueueManager for scheduling
            if self.task_queue:
                await self.task_queue.add_task(
                    task_id=task_id,
                    title=title,
                    urgency=urgency,
                    zone=zone,
                )

            return {
                "success": True,
                "result": f"タスク '{title}' を作成しました (ID: {task_id}, XP報酬: {xp_reward})",
            }
        else:
            return {"success": False, "error": "タスクの作成に失敗しました"}

    async def _handle_device_command(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Send command to edge device via MCPBridge with adaptive timeout."""
        agent_id = args.get("agent_id", "")
        tool_name = args.get("tool_name", "")

        # Parse arguments — may be JSON string or dict
        inner_args = args.get("arguments", {})
        if isinstance(inner_args, str):
            try:
                inner_args = json.loads(inner_args)
            except (json.JSONDecodeError, TypeError):
                inner_args = {}

        # Adaptive timeout from DeviceRegistry
        timeout = None
        if self.device_registry:
            timeout = self.device_registry.get_timeout_for_device(agent_id)

        result = await self.mcp.call_tool(agent_id, tool_name, inner_args, timeout=timeout)

        # Handle queued responses (command queued for sleeping device)
        if isinstance(result, dict) and result.get("status") == "queued":
            target = result.get("target", agent_id)
            return {
                "success": True,
                "result": f"コマンドをキューに追加: {target}/{tool_name} (デバイスの次回ウェイク時に配送)",
            }

        if result is not None:
            return {
                "success": True,
                "result": f"デバイスコマンド実行完了: {agent_id}/{tool_name} -> {json.dumps(result, ensure_ascii=False)}",
            }
        return {"success": False, "error": f"MCP call to {agent_id}/{tool_name} failed or timed out"}

    async def _handle_get_zone_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed zone status from WorldModel."""
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

    async def _handle_speak(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize speech and record as ephemeral voice event."""
        message = args.get("message", "")
        zone = args.get("zone", "")
        tone = args.get("tone", "neutral")

        # 1. Call voice service to synthesize text directly
        audio_url = None
        if self._session:
            try:
                async with self._session.post(
                    f"{self.voice_url}/api/voice/synthesize",
                    json={"text": message},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        audio_url = data.get("audio_url")
                    else:
                        logger.warning(f"Voice synthesize failed: {resp.status}")
            except Exception as e:
                logger.warning(f"Voice synthesize error: {e}")

            # 2. Record voice event in dashboard backend
            try:
                await self._session.post(
                    f"{self.dashboard_api_url}/voice-events/",
                    json={
                        "message": message,
                        "audio_url": audio_url or "",
                        "zone": zone,
                        "tone": tone,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                )
            except Exception as e:
                logger.warning(f"Failed to record voice event: {e}")
        else:
            # Fallback: use dashboard client speak method
            result = await self.dashboard.speak(message, zone, tone)
            if not result:
                return {"success": False, "error": "Speak failed"}

        # Record successful speak for cooldown tracking
        self.sanitizer.record_speak(zone=zone or "general")

        return {
            "success": True,
            "result": f"「{message}」を音声で通知しました",
        }

    async def _handle_get_active_tasks(self) -> Dict[str, Any]:
        """Get active tasks from DashboardClient."""
        tasks = await self.dashboard.get_active_tasks()
        if not tasks:
            return {"success": True, "result": "アクティブなタスクはありません"}

        summaries = []
        for t in tasks[:10]:  # Limit to 10
            title = t.get("title", "")
            completed = t.get("is_completed", False)
            zone = t.get("zone", "")
            task_type = t.get("task_type", [])
            status_str = "完了" if completed else "対応中"
            zone_str = f", zone: {zone}" if zone else ""
            type_str = f", type: {','.join(task_type)}" if task_type else ""
            summaries.append(f"- {title} ({status_str}{zone_str}{type_str})")

        return {
            "success": True,
            "result": f"アクティブなタスク ({len(tasks)}件):\n" + "\n".join(summaries),
        }

    async def _handle_get_device_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get device network status from DeviceRegistry."""
        if not self.device_registry:
            return {"success": False, "error": "DeviceRegistry が初期化されていません"}

        zone_id = args.get("zone_id")
        tree = self.device_registry.get_device_tree(zone_id=zone_id)
        return {"success": True, "result": tree}

    # --- PC tools (OpenClaw) ---

    async def _handle_get_pc_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
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

    async def _handle_run_pc_command(self, args: Dict[str, Any]) -> Dict[str, Any]:
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

    async def _handle_control_browser(self, args: Dict[str, Any]) -> Dict[str, Any]:
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

    async def _handle_send_pc_notification(self, args: Dict[str, Any]) -> Dict[str, Any]:
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

    # --- Service tools ---

    async def _handle_get_service_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
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

    # --- Obsidian tools ---

    async def _handle_search_notes(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.obsidian_url:
            return {"success": False, "error": "Obsidian bridge not configured"}
        try:
            async with self._session.post(
                f"{self.obsidian_url}/api/notes/search",
                json={
                    "query": args.get("query", ""),
                    "tags": args.get("tags"),
                    "path_prefix": args.get("path_prefix"),
                    "max_results": args.get("max_results", 5),
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_write_note(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.obsidian_url:
            return {"success": False, "error": "Obsidian bridge not configured"}
        try:
            async with self._session.post(
                f"{self.obsidian_url}/api/notes/write",
                json={
                    "title": args.get("title", ""),
                    "content": args.get("content", ""),
                    "tags": args.get("tags"),
                    "category": args.get("category"),
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_recent_notes(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.obsidian_url:
            return {"success": False, "error": "Obsidian bridge not configured"}
        try:
            async with self._session.get(
                f"{self.obsidian_url}/api/notes/recent",
                params={"limit": args.get("limit", 5)},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Home Assistant tools ---

    async def _handle_control_light(self, args: Dict[str, Any]) -> Dict[str, Any]:
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

    async def _handle_control_climate(self, args: Dict[str, Any]) -> Dict[str, Any]:
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
            # Set mode first, then temperature
            await self._ha_service_call(entity_id, "climate/set_hvac_mode", {"hvac_mode": mode})
            return await self._ha_service_call(entity_id, "climate/set_temperature", {
                "temperature": data["temperature"],
                **({"fan_mode": data["fan_mode"]} if "fan_mode" in data else {}),
            })
        return await self._ha_service_call(entity_id, service, data)

    async def _handle_control_cover(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.ha_url:
            return {"success": False, "error": "HA bridge not configured"}
        entity_id = args.get("entity_id", "")
        action = args.get("action")
        position = args.get("position")

        if position is not None:
            return await self._ha_service_call(entity_id, "cover/set_cover_position",
                                               {"position": position})
        if action == "open":
            return await self._ha_service_call(entity_id, "cover/open_cover")
        elif action == "close":
            return await self._ha_service_call(entity_id, "cover/close_cover")
        elif action == "stop":
            return await self._ha_service_call(entity_id, "cover/stop_cover")
        return {"success": False, "error": "No action or position specified"}

    async def _handle_get_home_devices(self, args: Dict[str, Any]) -> Dict[str, Any]:
        hd = self.world_model.home_devices
        status = {
            "bridge_connected": hd.bridge_connected,
            "lights": {
                eid: {"on": l.on, "brightness": l.brightness}
                for eid, l in hd.lights.items()
            },
            "climates": {
                eid: {"mode": c.mode, "target_temp": c.target_temp, "current_temp": c.current_temp}
                for eid, c in hd.climates.items()
            },
            "covers": {
                eid: {"position": c.position, "is_open": c.is_open}
                for eid, c in hd.covers.items()
            },
            "switches": hd.switches,
        }
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    # --- Biometric tools ---

    async def _handle_get_biometrics(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get current biometric readings from world model."""
        bio = self.world_model.biometric_state
        status = {"bridge_connected": bio.bridge_connected, "provider": bio.provider}
        if bio.heart_rate.bpm is not None:
            status["heart_rate"] = {
                "bpm": bio.heart_rate.bpm,
                "zone": bio.heart_rate.zone,
                "resting_bpm": bio.heart_rate.resting_bpm,
            }
        if bio.spo2.percent is not None:
            status["spo2"] = {"percent": bio.spo2.percent}
        if bio.stress.last_update > 0:
            status["stress"] = {"level": bio.stress.level, "category": bio.stress.category}
        if bio.fatigue.last_update > 0:
            status["fatigue"] = {"score": bio.fatigue.score, "factors": bio.fatigue.factors}
        if bio.activity.last_update > 0:
            status["activity"] = {
                "steps": bio.activity.steps,
                "steps_goal": bio.activity.steps_goal,
                "calories": bio.activity.calories,
                "level": bio.activity.level,
            }
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    async def _handle_get_sleep_summary(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get sleep data from world model or bridge API."""
        bio = self.world_model.biometric_state
        if bio.sleep.last_update > 0:
            status = {
                "duration_minutes": bio.sleep.duration_minutes,
                "deep_minutes": bio.sleep.deep_minutes,
                "rem_minutes": bio.sleep.rem_minutes,
                "light_minutes": bio.sleep.light_minutes,
                "quality_score": bio.sleep.quality_score,
                "stage": bio.sleep.stage,
            }
            return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

        # Fallback: query bridge API
        if self.biometric_url:
            try:
                async with self._session.get(
                    f"{self.biometric_url}/api/biometric/sleep",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
                    if resp.status == 200 and data.get("status") != "no_data":
                        return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
            except Exception as e:
                logger.warning(f"Biometric bridge sleep query error: {e}")

        return {"success": True, "result": "睡眠データがまだありません"}

    # --- Perception tools ---

    async def _handle_get_perception_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get camera-based occupancy and activity data from world model."""
        zones_data = {}
        for zone_id, zone in self.world_model.zones.items():
            occ = zone.occupancy
            if occ.last_update > 0:
                zones_data[zone_id] = {
                    "person_count": occ.count,
                    "activity_level": occ.activity_level,
                    "activity_class": occ.activity_class,
                    "posture": occ.posture,
                    "posture_status": occ.posture_status,
                    "posture_duration_sec": occ.posture_duration_sec,
                    "last_update": occ.last_update,
                }
        if not zones_data:
            return {"success": True, "result": "カメラデータがまだありません"}
        return {"success": True, "result": json.dumps({"zones": zones_data}, ensure_ascii=False)}

    async def _ha_service_call(self, entity_id: str, service: str,
                               data: dict = None) -> Dict[str, Any]:
        """Call HA bridge REST API to execute a service call."""
        try:
            async with self._session.post(
                f"{self.ha_url}/api/device/control",
                json={
                    "entity_id": entity_id,
                    "service": service,
                    "data": data or {},
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                result = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": f"{service} -> {entity_id}"}
                return {"success": False, "error": result.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}
