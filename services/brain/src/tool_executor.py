"""
Tool executor — routes tool calls through sanitizer to handlers.
Forked from SOMS: extended with PC tools (OpenClaw), Obsidian tools, and
adaptive device timeout + queued response handling.
"""

import asyncio
import json
import os
import time
from typing import Any

import aiohttp
from loguru import logger

LOCALCRAW_BRIDGE_URL = os.getenv("LOCALCRAW_BRIDGE_URL", "")
OBSIDIAN_BRIDGE_URL = os.getenv("OBSIDIAN_BRIDGE_URL", "")
HA_BRIDGE_URL = os.getenv("HA_BRIDGE_URL", "")
BIOMETRIC_BRIDGE_URL = os.getenv("BIOMETRIC_BRIDGE_URL", "")
PERCEPTION_BRIDGE_URL = os.getenv("PERCEPTION_BRIDGE_URL", "")
SWITCHBOT_BRIDGE_URL = os.getenv("SWITCHBOT_BRIDGE_URL", "")
NEWS_BRIDGE_URL = os.getenv("NEWS_BRIDGE_URL", "")
KNOWLEDGE_BRIDGE_URL = os.getenv("KNOWLEDGE_BRIDGE_URL", "")
TAPO_BRIDGE_URL = os.getenv("TAPO_BRIDGE_URL", "")


def _internal_headers() -> dict:
    token = os.getenv("HEMS_INTERNAL_TOKEN", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


class ToolExecutor:
    def __init__(
        self,
        sanitizer,
        mcp_bridge,
        dashboard_client,
        world_model,
        task_queue,
        session: aiohttp.ClientSession = None,
        device_registry=None,
        device_dispatcher=None,
        scene_executor=None,
        persona_rewriter=None,
        power_mode_manager=None,
    ):
        self.sanitizer = sanitizer
        self.mcp = mcp_bridge
        self.dashboard = dashboard_client
        self.world_model = world_model
        self.task_queue = task_queue
        self._session = session
        self.device_registry = device_registry
        self.device_dispatcher = device_dispatcher
        self.scene_executor = scene_executor
        # Stage 2 (output) rewriter — applied to speak messages before TTS.
        # Kept optional (None) so this module works in test contexts without a live LLM.
        self.persona_rewriter = persona_rewriter
        # Power mode manager — used to gate persona rewrite under low-power mode
        # (skipped together with VLM model swap; matches the legacy gate that
        # used to live in main.Brain._run_rule_actions).
        self.power_mode_manager = power_mode_manager
        self.openclaw_url = LOCALCRAW_BRIDGE_URL
        self.obsidian_url = OBSIDIAN_BRIDGE_URL
        self.ha_url = HA_BRIDGE_URL
        self.biometric_url = BIOMETRIC_BRIDGE_URL
        self.perception_url = PERCEPTION_BRIDGE_URL
        self.switchbot_url = SWITCHBOT_BRIDGE_URL
        self.news_url = NEWS_BRIDGE_URL
        self.knowledge_url = KNOWLEDGE_BRIDGE_URL
        self.tapo_url = TAPO_BRIDGE_URL
        self.voice_url = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")
        self.dashboard_api_url = os.getenv("DASHBOARD_API_URL", "http://backend:8000")

        # Motion retriever for avatar gesture selection
        try:
            from motion_retriever import MotionRetriever

            self.motion_retriever = MotionRetriever()
        except Exception as e:
            logger.warning(f"Motion retriever init failed: {e}")
            self.motion_retriever = None

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
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
            elif tool_name == "get_sensor_history":
                return await self._handle_get_sensor_history(arguments)
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
            elif tool_name == "list_note_tags":
                return await self._handle_list_note_tags(arguments)
            elif tool_name == "control_light":
                return await self._handle_control_light(arguments)
            elif tool_name == "control_climate":
                return await self._handle_control_climate(arguments)
            elif tool_name == "control_cover":
                return await self._handle_control_cover(arguments)
            elif tool_name == "get_home_devices":
                return await self._handle_get_home_devices(arguments)
            elif tool_name == "control_switch":
                return await self._handle_control_switch(arguments)
            elif tool_name == "get_sensor_data":
                return await self._handle_get_sensor_data(arguments)
            elif tool_name == "execute_scene":
                return await self._handle_execute_scene(arguments)
            elif tool_name == "set_guest_mode":
                return self._handle_set_guest_mode(arguments)
            elif tool_name == "get_weather":
                return self._handle_get_weather(arguments)
            elif tool_name == "get_biometrics":
                return await self._handle_get_biometrics(arguments)
            elif tool_name == "get_sleep_summary":
                return await self._handle_get_sleep_summary(arguments)
            elif tool_name == "get_biometric_trend":
                return await self._handle_get_biometric_trend(arguments)
            elif tool_name == "get_sleep_history":
                return await self._handle_get_sleep_history(arguments)
            elif tool_name == "get_perception_status":
                return await self._handle_get_perception_status(arguments)
            elif tool_name == "describe_scene":
                return await self._handle_describe_scene(arguments)
            elif tool_name == "list_cameras":
                return await self._handle_list_cameras(arguments)
            elif tool_name == "get_vlm_status":
                return await self._handle_get_vlm_status(arguments)
            elif tool_name == "get_activity_history":
                return await self._handle_get_activity_history(arguments)
            elif tool_name == "list_scene_objects":
                return await self._handle_list_scene_objects(arguments)
            elif tool_name == "get_scene_timeline":
                return await self._handle_get_scene_timeline(arguments)
            elif tool_name == "add_shopping_item":
                return await self._handle_add_shopping_item(arguments)
            elif tool_name == "get_shopping_list":
                return await self._handle_get_shopping_list(arguments)
            elif tool_name == "get_switchbot_devices":
                return await self._handle_get_switchbot_devices(arguments)
            elif tool_name == "control_switchbot":
                return await self._handle_control_switchbot(arguments)
            elif tool_name == "send_switchbot_ir":
                return await self._handle_send_switchbot_ir(arguments)
            elif tool_name == "get_news_summary":
                return await self._handle_get_news_summary(arguments)
            elif tool_name == "get_recent_emails":
                return await self._handle_get_recent_emails(arguments)
            elif tool_name == "gas_query_free_slots":
                return await self._handle_gas_query_free_slots(arguments)
            elif tool_name == "gas_query_sheet":
                return await self._handle_gas_query_sheet(arguments)
            elif tool_name == "get_entity_status":
                return await self._handle_get_entity_status(arguments)
            elif tool_name == "get_power_consumption":
                return await self._handle_get_power_consumption(arguments)
            elif tool_name == "list_processes":
                return await self._handle_list_processes(arguments)
            elif tool_name == "search_knowledge":
                return await self._handle_search_knowledge(arguments)
            elif tool_name == "get_knowledge_sources":
                return await self._handle_get_knowledge_sources(arguments)
            elif tool_name == "read_knowledge_document":
                return await self._handle_read_knowledge_document(arguments)
            elif tool_name == "get_recent_knowledge_changes":
                return await self._handle_get_recent_knowledge_changes(arguments)
            elif tool_name == "control_actuator":
                return await self._handle_control_actuator(arguments)
            elif tool_name == "list_devices":
                return await self._handle_list_devices(arguments)
            elif tool_name == "describe_device":
                return await self._handle_describe_device(arguments)
            elif tool_name == "zigbee_permit_join":
                return await self._handle_zigbee_permit_join(arguments)
            elif tool_name == "execute_scene_by_name":
                return await self._handle_execute_scene_by_name(arguments)
            elif tool_name == "list_scenes":
                return await self._handle_list_scenes(arguments)
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {"success": False, "error": str(e)}

    async def _handle_create_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Create a task via DashboardClient and register with TaskQueueManager."""
        title = args.get("title", "")
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
                "result": f"タスク '{title}' を作成しました (ID: {task_id})",
            }
        else:
            return {"success": False, "error": "タスクの作成に失敗しました"}

    async def _handle_device_command(self, args: dict[str, Any]) -> dict[str, Any]:
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

    async def _handle_get_zone_status(self, args: dict[str, Any]) -> dict[str, Any]:
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
                {"type": e.event_type, "description": e.description, "severity": e.severity} for e in zone.events[-5:]
            ],
        }
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    async def _handle_get_sensor_history(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return a sensor history window from the event store.

        For windows ≤ 24h: query raw_events directly (high resolution).
        For windows > 24h: query hourly_aggregates (lower resolution, longer reach).
        Setting `aggregate=true` forces aggregate path even at small windows.
        """
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import text as _sql

        from event_store.database import get_engine

        zone = str(args.get("zone", "")).strip()
        channel = str(args.get("channel", "")).strip()
        hours = int(args.get("hours", 6) or 6)
        max_points = int(args.get("max_points", 200) or 200)
        force_aggregate = bool(args.get("aggregate", False))
        hours = max(1, min(hours, 720))  # up to 30 days now
        max_points = max(1, min(max_points, 1000))

        if not zone or not channel:
            return {"success": False, "error": "zone and channel are required"}

        engine = get_engine()
        if engine is None:
            return {
                "success": True,
                "result": json.dumps(
                    {"zone": zone, "channel": channel, "points": [], "note": "event store disabled"},
                    ensure_ascii=False,
                ),
            }

        is_postgres = "postgresql" in os.getenv("DATABASE_URL", "")
        schema = "events." if is_postgres else ""
        since = datetime.now(UTC) - timedelta(hours=hours)
        use_aggregate = force_aggregate or hours > 24

        try:
            async with engine.begin() as conn:
                if use_aggregate:
                    # hourly_aggregates.zones is JSON: { zone_id: { channel: {min,max,avg,...} } }
                    rows = (
                        await conn.execute(
                            _sql(
                                f"""
                                SELECT period_start, zones FROM {schema}hourly_aggregates
                                WHERE period_start >= :since
                                ORDER BY period_start ASC
                                LIMIT :lim
                                """
                            ),
                            {"since": since, "lim": max_points},
                        )
                    ).fetchall()

                    points: list[dict] = []
                    for ts, raw in rows:
                        try:
                            zones_data = raw if isinstance(raw, dict) else json.loads(raw or "{}")
                        except Exception:
                            continue
                        zone_data = zones_data.get(zone, {})
                        ch_data = zone_data.get(channel) if isinstance(zone_data, dict) else None
                        if ch_data is None:
                            continue
                        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                        if isinstance(ch_data, dict):
                            points.append(
                                {
                                    "t": ts_str,
                                    "min": ch_data.get("min"),
                                    "max": ch_data.get("max"),
                                    "avg": ch_data.get("avg"),
                                    "v": ch_data.get("avg"),
                                }
                            )
                        else:
                            points.append({"t": ts_str, "v": ch_data})

                    values = [p["v"] for p in points if isinstance(p.get("v"), (int, float))]
                    summary = None
                    if values:
                        summary = {
                            "count": len(values),
                            "min": min(values),
                            "max": max(values),
                            "avg": sum(values) / len(values),
                            "last": values[-1],
                        }
                    return {
                        "success": True,
                        "result": json.dumps(
                            {
                                "zone": zone,
                                "channel": channel,
                                "hours": hours,
                                "resolution": "hourly_aggregate",
                                "points": points,
                                "summary": summary,
                            },
                            ensure_ascii=False,
                        ),
                    }

                rows = (
                    await conn.execute(
                        _sql(
                            f"""
                            SELECT timestamp, data FROM {schema}raw_events
                            WHERE zone = :zone
                              AND event_type = 'sensor_reading'
                              AND timestamp >= :since
                            ORDER BY timestamp DESC
                            LIMIT :lim
                            """
                        ),
                        {"zone": zone, "since": since, "lim": max_points * 4},
                    )
                ).fetchall()
        except Exception as e:
            logger.warning(f"get_sensor_history query failed: {e}")
            return {"success": False, "error": f"query failed: {e}"}

        points: list[dict] = []
        for ts, raw in rows:
            try:
                data = raw if isinstance(raw, dict) else json.loads(raw or "{}")
            except Exception:
                continue
            if data.get("channel") != channel:
                continue
            ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            points.append({"t": ts_str, "v": data.get("value")})
            if len(points) >= max_points:
                break

        points.reverse()  # chronological order

        values = [p["v"] for p in points if isinstance(p["v"], (int, float))]
        summary = None
        if values:
            summary = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "last": values[-1],
            }

        result = {
            "zone": zone,
            "channel": channel,
            "hours": hours,
            "resolution": "raw",
            "points": points,
            "summary": summary,
        }
        return {"success": True, "result": json.dumps(result, ensure_ascii=False)}

    async def _handle_speak(self, args: dict[str, Any]) -> dict[str, Any]:
        """Synthesize speech and record as ephemeral voice event.

        Stage 2 character overlay: if a PersonaRewriter is wired, rewrite the raw
        Stage-1 message into the configured character voice before synthesis.
        Fact-bearing tokens (numbers, device_ids, names) are preserved by the
        rewriter's system prompt.

        Rewrite is skipped when:
          - caller passes ``_skip_persona_rewrite=True`` (internal callers that
            already produced character-styled text, or rule actions explicitly
            requesting raw output)
          - PowerModeManager reports low-power mode (latency > character voice)
          - VLM heavy model swap is active (LLM path is contended)
        """
        raw_message = args.get("message", "")
        zone = args.get("zone", "")
        tone = args.get("tone", "neutral")
        skip_rewrite = bool(args.get("_skip_persona_rewrite", False))

        # Stage 2 rewrite (empty message / opt-out / gated → bypass)
        message = raw_message
        low_power = bool(self.power_mode_manager and self.power_mode_manager.is_low_power)
        vlm_swap = bool(getattr(self.world_model, "vlm_model_swap_active", False))
        if (
            not skip_rewrite
            and self.persona_rewriter is not None
            and raw_message
            and not low_power
            and not vlm_swap
        ):
            try:
                message = await self.persona_rewriter.rewrite(raw_message, tone=tone)
            except Exception as e:
                logger.debug(f"Persona rewrite failed, using raw: {e}")
                message = raw_message

        # 1. Select avatar motion via serendipity retriever
        motion_id = None
        if self.motion_retriever:
            try:
                motion_id = self.motion_retriever.select(message, tone)
            except Exception as e:
                logger.warning(f"Motion retriever error: {e}")

        # 2. Call voice service to synthesize text directly
        audio_url = None
        if self._session:
            try:
                async with self._session.post(
                    f"{self.voice_url}/api/voice/synthesize",
                    json={"text": message, "tone": tone},
                    headers=_internal_headers(),
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        audio_url = data.get("audio_url")
                    else:
                        logger.warning(f"Voice synthesize failed: {resp.status}")
            except Exception as e:
                logger.warning(f"Voice synthesize error: {e}")

            # 3. Record voice event in dashboard backend
            try:
                await self._session.post(
                    f"{self.dashboard_api_url}/voice-events/",
                    json={
                        "message": message,
                        "audio_url": audio_url or "",
                        "zone": zone,
                        "tone": tone,
                        "motion_id": motion_id,
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
            "motion_id": motion_id,
        }

    async def _handle_get_active_tasks(self) -> dict[str, Any]:
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

    async def _handle_get_device_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get device network status from DeviceRegistry."""
        if not self.device_registry:
            return {"success": False, "error": "DeviceRegistry が初期化されていません"}

        zone_id = args.get("zone_id")
        tree = self.device_registry.get_device_tree(zone_id=zone_id)
        return {"success": True, "result": tree}

    # --- PC tools (OpenClaw) ---

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

    # --- Service tools ---

    async def _handle_get_service_status(self, args: dict[str, Any]) -> dict[str, Any]:
        ss = self.world_model.services_state
        service_name = args.get("service_name")
        if service_name:
            svc = ss.services.get(service_name)
            if not svc:
                return {"success": False, "error": f"Service '{service_name}' not found"}
            status = {
                "name": svc.name,
                "available": svc.available,
                "unread_count": svc.unread_count,
                "summary": svc.summary,
                "last_check": svc.last_check,
                "error": svc.error,
            }
        else:
            status = {
                name: {
                    "name": svc.name,
                    "available": svc.available,
                    "unread_count": svc.unread_count,
                    "summary": svc.summary,
                    "last_check": svc.last_check,
                    "error": svc.error,
                }
                for name, svc in ss.services.items()
            }
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    # --- Obsidian tools ---

    async def _handle_search_notes(self, args: dict[str, Any]) -> dict[str, Any]:
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

    async def _handle_write_note(self, args: dict[str, Any]) -> dict[str, Any]:
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

    async def _handle_get_recent_notes(self, args: dict[str, Any]) -> dict[str, Any]:
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

    async def _handle_list_note_tags(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.obsidian_url:
            return {"success": False, "error": "Obsidian bridge not configured"}
        try:
            async with self._session.get(
                f"{self.obsidian_url}/api/notes/tags",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Home Assistant tools ---

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
            # Set mode first, then temperature
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

    # --- System tools ---

    def _handle_set_guest_mode(self, args: dict[str, Any]) -> dict[str, Any]:
        enabled = args.get("enabled", False)
        duration = args.get("duration_hours", 4)
        self.world_model.set_guest_mode(enabled, duration)
        return {"success": True, "result": f"ゲストモード{'ON' if enabled else 'OFF'} ({duration}時間)"}

    def _handle_get_weather(self, args: dict[str, Any]) -> dict[str, Any]:
        w = self.world_model.weather
        if w.last_update == 0:
            return {"success": True, "result": "天気データなし"}
        forecast = [
            {
                "datetime": f.datetime,
                "condition": f.condition,
                "temperature": f.temperature,
                "precipitation": f.precipitation_probability,
            }
            for f in w.forecast[:6]
        ]
        result = {
            "condition": w.condition,
            "temperature": w.temperature,
            "humidity": w.humidity,
            "wind_speed": w.wind_speed,
            "forecast": forecast,
        }
        return {"success": True, "result": json.dumps(result, ensure_ascii=False)}

    # --- Biometric tools ---

    async def _handle_get_biometrics(self, args: dict[str, Any]) -> dict[str, Any]:
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

    async def _handle_get_sleep_summary(self, args: dict[str, Any]) -> dict[str, Any]:
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

    async def _handle_get_biometric_trend(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return time-series for a biometric metric from BiometricState.history."""
        metric = (args.get("metric") or "").strip()
        if not metric:
            return {"success": False, "error": "metric is required"}
        window_hours = max(1, min(float(args.get("window_hours", 24)), 168))
        max_samples = max(10, min(int(args.get("max_samples", 100)), 500))

        bio = self.world_model.biometric_state
        history = bio.history.get(metric) if bio.history else None
        if not history:
            return {
                "success": True,
                "result": json.dumps(
                    {"metric": metric, "samples": [], "count": 0, "reason": "no history"},
                    ensure_ascii=False,
                ),
            }

        cutoff = time.time() - window_hours * 3600
        samples = [(ts, v) for ts, v in history if ts >= cutoff]
        if len(samples) > max_samples:
            step = len(samples) // max_samples
            samples = samples[::step][:max_samples]

        if samples:
            values = [v for _, v in samples]
            stats = {
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 2),
                "first_ts": samples[0][0],
                "last_ts": samples[-1][0],
            }
        else:
            stats = {}

        return {
            "success": True,
            "result": json.dumps(
                {
                    "metric": metric,
                    "window_hours": window_hours,
                    "count": len(samples),
                    "samples": [{"ts": ts, "value": v} for ts, v in samples],
                    "stats": stats,
                },
                ensure_ascii=False,
            ),
        }

    async def _handle_get_sleep_history(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return last N days of sleep quality + duration history."""
        days = max(1, min(int(args.get("days", 7)), 14))

        bio = self.world_model.biometric_state
        quality_hist = bio.history.get("sleep_quality") if bio.history else None
        duration_hist = bio.history.get("sleep_duration") if bio.history else None

        cutoff = time.time() - days * 86400
        quality = [(ts, v) for ts, v in (quality_hist or []) if ts >= cutoff]
        duration = [(ts, v) for ts, v in (duration_hist or []) if ts >= cutoff]

        sessions = []
        # Pair quality and duration by index (insertion order ≈ same nights)
        for idx in range(max(len(quality), len(duration))):
            entry = {}
            if idx < len(quality):
                ts, q = quality[idx]
                entry["timestamp"] = ts
                entry["quality_score"] = q
            if idx < len(duration):
                ts, d = duration[idx]
                entry.setdefault("timestamp", ts)
                entry["duration_minutes"] = d
            sessions.append(entry)

        avg_quality = round(sum(v for _, v in quality) / len(quality), 1) if quality else None
        avg_duration = round(sum(v for _, v in duration) / len(duration), 1) if duration else None

        return {
            "success": True,
            "result": json.dumps(
                {
                    "days": days,
                    "sessions": sessions,
                    "avg_quality": avg_quality,
                    "avg_duration_minutes": avg_duration,
                    "session_count": len(sessions),
                },
                ensure_ascii=False,
            ),
        }

    # --- Perception tools ---

    async def _handle_get_perception_status(self, args: dict[str, Any]) -> dict[str, Any]:
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

    async def _handle_describe_scene(self, args: dict[str, Any]) -> dict[str, Any]:
        """Analyze camera scene via VLM (on-demand). Uses cached data if recent."""
        zone_id = args.get("zone_id", "")
        custom_prompt = args.get("prompt", "")

        # Check cached VLM data in world_model (if <60s old and no custom prompt)
        if not custom_prompt:
            for zid, zone in self.world_model.zones.items():
                if zone_id and zid != zone_id:
                    continue
                occ = zone.occupancy
                import time as _time

                if occ.vlm_last_update > 0 and _time.time() - occ.vlm_last_update < 60:
                    data = {
                        "zone": zid,
                        "description": occ.scene_description,
                        "objects": occ.scene_objects,
                        "scene_type": occ.scene_type,
                        "anomalies": occ.scene_anomalies,
                        "cached": True,
                    }
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}

        # On-demand request to perception service
        if not self.perception_url:
            return {"success": False, "error": "Perception bridge not configured"}
        try:
            async with self._session.post(
                f"{self.perception_url}/api/perception/vlm/analyze",
                json={
                    "zone_id": zone_id or None,
                    "prompt": custom_prompt or None,
                },
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    if data.get("error"):
                        return {"success": False, "error": data["error"]}
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except TimeoutError:
            return {"success": False, "error": "VLM分析がタイムアウトしました"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_list_scene_objects(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return unique objects seen in the zone's VLM history within the time window."""
        import time as _time

        zone_id = args.get("zone_id", "")
        if not zone_id:
            return {"success": False, "error": "zone_id required"}
        since_minutes = int(args.get("since_minutes", 60) or 60)
        since_minutes = max(1, min(since_minutes, 60))
        cutoff = _time.time() - since_minutes * 60

        zone = self.world_model.zones.get(zone_id)
        if not zone:
            return {"success": True, "result": json.dumps({"zone": zone_id, "objects": []}, ensure_ascii=False)}

        seen: dict[str, dict[str, Any]] = {}
        for snap in zone.occupancy.vlm_history:
            if snap.timestamp < cutoff:
                continue
            for obj in snap.objects:
                entry = seen.setdefault(obj, {"count": 0, "last_seen": 0})
                entry["count"] += 1
                entry["last_seen"] = max(entry["last_seen"], snap.timestamp)
        objects = sorted(
            (
                {"name": name, "count": info["count"], "last_seen_ago_sec": int(_time.time() - info["last_seen"])}
                for name, info in seen.items()
            ),
            key=lambda x: (-x["count"], x["last_seen_ago_sec"]),
        )
        return {
            "success": True,
            "result": json.dumps(
                {"zone": zone_id, "since_minutes": since_minutes, "objects": objects[:30]},
                ensure_ascii=False,
            ),
        }

    async def _handle_get_scene_timeline(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the VLM scene history (latest 10) as a time-ordered list."""
        import time as _time

        zone_id = args.get("zone_id", "")
        if not zone_id:
            return {"success": False, "error": "zone_id required"}
        zone = self.world_model.zones.get(zone_id)
        if not zone or not zone.occupancy.vlm_history:
            return {"success": True, "result": json.dumps({"zone": zone_id, "timeline": []}, ensure_ascii=False)}

        now = _time.time()
        timeline = [
            {
                "age_sec": int(now - s.timestamp),
                "description": s.description[:200],
                "scene_type": s.scene_type,
                "objects": s.objects[:8],
                "anomalies": s.anomalies[:3],
                "tier": s.tier,
            }
            for s in zone.occupancy.vlm_history
        ]
        return {
            "success": True,
            "result": json.dumps({"zone": zone_id, "timeline": timeline}, ensure_ascii=False),
        }

    async def _handle_list_cameras(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.perception_url:
            return {"success": False, "error": "Perception bridge not configured"}
        try:
            async with self._session.get(
                f"{self.perception_url}/api/perception/cameras",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_vlm_status(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.perception_url:
            return {"success": False, "error": "Perception bridge not configured"}
        try:
            async with self._session.get(
                f"{self.perception_url}/api/perception/vlm/status",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_activity_history(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return per-zone activity/scene snapshots from world_model in chronological order."""
        zone_id = args.get("zone_id", "")
        if not zone_id:
            return {"success": False, "error": "zone_id required"}
        limit = max(1, min(int(args.get("limit", 10)), 30))

        zone = self.world_model.zones.get(zone_id)
        if not zone:
            return {"success": True, "result": json.dumps({"zone": zone_id, "snapshots": []}, ensure_ascii=False)}

        now = time.time()
        snapshots = [
            {
                "age_sec": int(now - s.timestamp),
                "scene_type": s.scene_type,
                "anomalies": s.anomalies[:3],
                "object_count": len(s.objects),
                "description": s.description[:120],
                "tier": s.tier,
            }
            for s in list(zone.occupancy.vlm_history)[-limit:]
        ]
        return {
            "success": True,
            "result": json.dumps(
                {
                    "zone": zone_id,
                    "current_activity_level": zone.occupancy.activity_level,
                    "current_posture": zone.occupancy.posture,
                    "snapshots": snapshots,
                },
                ensure_ascii=False,
            ),
        }

    # --- Shopping tools ---

    async def _handle_add_shopping_item(self, args: dict[str, Any]) -> dict[str, Any]:
        """Add item to shopping list via backend API."""
        name = args.get("name", "")
        try:
            async with self._session.post(
                f"{self.dashboard_api_url}/shopping/",
                json={
                    "name": name,
                    "category": args.get("category"),
                    "quantity": args.get("quantity", 1),
                    "unit": args.get("unit"),
                    "store": args.get("store"),
                    "price": args.get("price"),
                    "is_recurring": args.get("is_recurring", False),
                    "recurrence_days": args.get("recurrence_days"),
                    "priority": args.get("priority", 1),
                    "created_by": "brain",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": f"買い物リストに「{name}」を追加しました"}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_shopping_list(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get shopping list from backend API."""
        params = {}
        if args.get("category"):
            params["category"] = args["category"]
        if args.get("store"):
            params["store"] = args["store"]
        try:
            async with self._session.get(
                f"{self.dashboard_api_url}/shopping/",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    if not data:
                        return {"success": True, "result": "買い物リストは空です"}
                    items = []
                    for item in data[:15]:
                        name = item.get("name", "")
                        qty = item.get("quantity", 1)
                        cat = item.get("category", "")
                        store = item.get("store", "")
                        price = item.get("price")
                        parts = [f"- {name}"]
                        if qty > 1:
                            unit = item.get("unit", "個")
                            parts.append(f" x{qty}{unit}")
                        if cat:
                            parts.append(f" [{cat}]")
                        if store:
                            parts.append(f" @{store}")
                        if price:
                            parts.append(f" ¥{price}")
                        if item.get("is_recurring"):
                            parts.append(" (定期)")
                        items.append("".join(parts))
                    return {"success": True, "result": f"買い物リスト ({len(data)}件):\n" + "\n".join(items)}
                return {"success": False, "error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- News tools ---

    async def _handle_get_news_summary(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get latest news summary from world model cache or news-bridge API."""
        ns = self.world_model.news_state

        # Try cached data first
        if ns.daily_timestamp > 0:
            import time as _time

            age_min = int((_time.time() - ns.daily_timestamp) / 60)
            result = {
                "summary": ns.daily_summary,
                "chunks": ns.daily_chunks,
                "article_count": len(ns.daily_chunks),
                "age_minutes": age_min,
            }
            if ns.urgent_articles:
                recent = [a for a in ns.urgent_articles if _time.time() - a.get("timestamp", 0) < 3600]
                if recent:
                    result["urgent"] = recent
            return {"success": True, "result": json.dumps(result, ensure_ascii=False)}

        # Fallback: query news-bridge API
        if self.news_url and self._session:
            try:
                async with self._session.get(
                    f"{self.news_url}/api/news/latest",
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                    return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": True, "result": "ニュースデータがまだありません"}

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
                # Strip "tapo." prefix to get vendor_ref
                vendor_ref = device_id.removeprefix("tapo.")
                async with self._session.get(
                    f"{self.tapo_url}/api/devices/{vendor_ref}/status",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return {"success": True, "result": json.dumps(await resp.json(), ensure_ascii=False)}
                    return {"success": False, "error": f"HTTP {resp.status}"}
            # All plugs — list, then fan-out status reads in parallel
            async with self._session.get(
                f"{self.tapo_url}/api/devices",
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
        return {"success": True, "result": json.dumps({"processes": result, "total": len(filtered)}, ensure_ascii=False)}

    async def _handle_get_recent_emails(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get recent Gmail threads from world_model.gas_state.gmail_recent."""
        gs = self.world_model.gas_state
        threads = gs.gmail_recent or []
        if not threads:
            return {"success": True, "result": "Gmailスレッド情報がありません"}

        limit = max(1, min(int(args.get("limit", 10)), 50))
        sender_q = (args.get("sender_contains") or "").lower()
        subject_q = (args.get("subject_contains") or "").lower()
        unread_only = bool(args.get("unread_only", False))

        results = []
        for t in threads:
            if not isinstance(t, dict):
                continue
            sender = str(t.get("from") or t.get("sender") or "")
            subject = str(t.get("subject") or "")
            snippet = str(t.get("snippet") or "")
            unread = bool(t.get("unread", False))
            if unread_only and not unread:
                continue
            if sender_q and sender_q not in sender.lower():
                continue
            if subject_q and subject_q not in subject.lower():
                continue
            results.append(
                {
                    "from": sender[:80],
                    "subject": subject[:100],
                    "snippet": snippet[:50],
                    "unread": unread,
                    "thread_id": t.get("thread_id") or t.get("id"),
                }
            )
            if len(results) >= limit:
                break

        return {
            "success": True,
            "result": json.dumps({"threads": results, "total": len(results)}, ensure_ascii=False),
        }

    async def _handle_gas_query_free_slots(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return calendar free slots with HH:MM-HH:MM ranges from gas_state.free_slots."""
        from datetime import datetime as _dt

        gs = self.world_model.gas_state
        if not gs.free_slots:
            return {"success": True, "result": "空きスロット情報がありません"}

        date_range_hours = max(1, min(int(args.get("date_range_hours", 24)), 168))
        min_minutes = max(15, min(int(args.get("min_duration_minutes", 60)), 480))
        limit = max(1, min(int(args.get("limit", 5)), 20))

        cutoff_ts = time.time() + date_range_hours * 3600
        results = []
        for slot in gs.free_slots:
            if slot.duration_minutes < min_minutes:
                continue
            try:
                start_dt = _dt.fromisoformat(slot.start.replace("Z", "+00:00"))
                end_dt = _dt.fromisoformat(slot.end.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            if start_dt.timestamp() > cutoff_ts:
                continue
            results.append(
                {
                    "start": start_dt.strftime("%Y-%m-%d %H:%M"),
                    "end": end_dt.strftime("%Y-%m-%d %H:%M"),
                    "range": f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}",
                    "duration_minutes": slot.duration_minutes,
                }
            )
            if len(results) >= limit:
                break

        return {
            "success": True,
            "result": json.dumps({"slots": results, "total": len(results)}, ensure_ascii=False),
        }

    async def _handle_gas_query_sheet(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return cached sheet data from gas_state.sheets[name]."""
        gs = self.world_model.gas_state
        name = (args.get("name") or "").strip()
        if not name:
            return {"success": False, "error": "name is required"}

        sheet = gs.sheets.get(name)
        if not sheet:
            available = list(gs.sheets.keys())
            return {
                "success": True,
                "result": json.dumps(
                    {
                        "found": False,
                        "name": name,
                        "available_sheets": available[:20],
                    },
                    ensure_ascii=False,
                ),
            }

        max_rows = max(1, min(int(args.get("max_rows", 50)), 200))
        rows = sheet.values[:max_rows] if isinstance(sheet.values, list) else []
        return {
            "success": True,
            "result": json.dumps(
                {
                    "found": True,
                    "name": name,
                    "headers": sheet.headers,
                    "rows": rows,
                    "row_count": len(rows),
                    "total_rows": len(sheet.values) if isinstance(sheet.values, list) else 0,
                    "last_update": sheet.last_update,
                },
                ensure_ascii=False,
            ),
        }

    # --- SwitchBot tools ---

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

    # --- Knowledge tools ---

    async def _handle_search_knowledge(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.knowledge_url:
            return {"success": False, "error": "Knowledge bridge not configured"}
        try:
            async with self._session.post(
                f"{self.knowledge_url}/api/knowledge/search",
                json={
                    "query": args.get("query", ""),
                    "source": args.get("source"),
                    "doc_type": args.get("doc_type"),
                    "tags": args.get("tags"),
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

    async def _handle_get_knowledge_sources(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.knowledge_url:
            return {"success": False, "error": "Knowledge bridge not configured"}
        try:
            async with self._session.get(
                f"{self.knowledge_url}/api/knowledge/sources",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_read_knowledge_document(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.knowledge_url:
            return {"success": False, "error": "Knowledge bridge not configured"}
        try:
            async with self._session.get(
                f"{self.knowledge_url}/api/knowledge/read",
                params={"source": args.get("source", ""), "path": args.get("path", "")},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_recent_knowledge_changes(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.knowledge_url:
            return {"success": False, "error": "Knowledge bridge not configured"}
        try:
            params: dict[str, Any] = {"limit": int(args.get("limit", 10))}
            source = args.get("source")
            if source:
                params["source"] = source
            async with self._session.get(
                f"{self.knowledge_url}/api/knowledge/recent",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
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
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                result = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": f"{service} -> {entity_id}"}
                return {"success": False, "error": result.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Device Registry tools ---

    async def _handle_control_actuator(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.device_dispatcher is None:
            return {"success": False, "error": "Device dispatcher not configured"}
        device_id = args.get("device_id", "")
        action = args.get("action", "")
        params = args.get("params") or {}
        if not device_id or not action:
            return {"success": False, "error": "device_id and action are required"}
        result = await self.device_dispatcher.dispatch(device_id, action, params)
        # Push action to backend log (fire-and-forget; never block control flow)
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
