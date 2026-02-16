"""
Tool Executor: Routes tool calls through Sanitizer validation to handlers.
"""
import json
import os
from typing import Dict, Any
import aiohttp
from loguru import logger


class ToolExecutor:
    def __init__(self, sanitizer, mcp_bridge, dashboard_client, world_model, task_queue, session: aiohttp.ClientSession = None, device_registry=None):
        self.sanitizer = sanitizer
        self.mcp = mcp_bridge
        self.dashboard = dashboard_client
        self.world_model = world_model
        self.task_queue = task_queue
        self._session = session
        self.device_registry = device_registry
        self.voice_url = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")
        self.dashboard_api_url = os.getenv("DASHBOARD_API_URL", "http://backend:8000")

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call with validation.

        Returns:
            {"success": True, "result": "..."} or {"success": False, "error": "..."}
        """
        # Validate through Sanitizer
        is_safe, reason = self.sanitizer.validate_tool_call(tool_name, arguments)
        if not is_safe:
            logger.warning(f"Tool call REJECTED: {tool_name} - {reason}")
            return {"success": False, "error": reason}

        try:
            if tool_name == "create_task":
                return await self._handle_create_task(arguments)
            elif tool_name == "send_device_command":
                return await self._handle_device_command(arguments)
            elif tool_name == "speak":
                return await self._handle_speak(arguments)
            elif tool_name == "get_zone_status":
                return await self._handle_get_zone_status(arguments)
            elif tool_name == "get_active_tasks":
                return await self._handle_get_active_tasks()
            elif tool_name == "get_device_status":
                return await self._handle_get_device_status(arguments)
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {"success": False, "error": str(e)}

    async def _handle_create_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a task via DashboardClient and register with TaskQueueManager."""
        title = args.get("title", "")
        description = args.get("description", "")
        bounty = args.get("bounty", 1000)
        urgency = args.get("urgency", 2)
        zone = args.get("zone")

        # Parse task_types from comma-separated string
        task_types_str = args.get("task_types", "general")
        task_types = [t.strip() for t in task_types_str.split(",") if t.strip()]

        result = await self.dashboard.create_task(
            title=title,
            description=description,
            bounty=bounty,
            urgency=urgency,
            zone=zone,
            task_types=task_types,
        )

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
                "result": f"タスク '{title}' を作成しました (ID: {task_id}, 報酬: {bounty}pt)",
            }
        else:
            return {"success": False, "error": "タスクの作成に失敗しました"}

    async def _handle_speak(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize speech and record as ephemeral voice event."""
        message = args.get("message", "")
        zone = args.get("zone")
        tone = args.get("tone", "neutral")

        # 1. Call voice service to synthesize text directly
        audio_url = None
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

        # Record successful speak for cooldown tracking (H-5 fix)
        self.sanitizer.record_speak(zone=zone or "general")

        return {
            "success": True,
            "result": f"「{message}」を音声で通知しました",
        }

    async def _handle_device_command(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Send command to edge device via MCPBridge with adaptive timeout."""
        agent_id = args.get("agent_id", "")
        tool_name = args.get("tool_name", "")

        # Parse arguments (may be JSON string or dict)
        inner_args = args.get("arguments", "{}")
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

        return {
            "success": True,
            "result": f"デバイスコマンド実行完了: {agent_id}/{tool_name} -> {json.dumps(result, ensure_ascii=False)}",
        }

    async def _handle_get_zone_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed zone status from WorldModel."""
        zone_id = args.get("zone_id", "")
        zone = self.world_model.get_zone(zone_id)

        if zone is None:
            return {"success": False, "error": f"ゾーン '{zone_id}' が見つかりません"}

        # Build status string
        lines = [f"ゾーン: {zone_id}"]

        if zone.occupancy.person_count > 0:
            lines.append(f"在室: {zone.occupancy.person_count}名 ({zone.occupancy.activity_summary})")
        else:
            lines.append("在室: 無人")

        env = zone.environment
        if env.temperature is not None:
            lines.append(f"気温: {env.temperature:.1f}℃ ({env.thermal_comfort})")
        if env.humidity is not None:
            lines.append(f"湿度: {env.humidity:.0f}%")
        if env.co2 is not None:
            lines.append(f"CO2: {env.co2}ppm{'（換気必要）' if env.is_stuffy else ''}")
        if env.illuminance is not None:
            lines.append(f"照度: {env.illuminance:.0f}lux")

        if zone.devices:
            for dev_id, dev in zone.devices.items():
                lines.append(f"デバイス {dev.device_type}({dev_id}): {dev.power_state}")

        return {"success": True, "result": "\n".join(lines)}

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
