import asyncio
import os
import json
import time
import aiohttp
from loguru import logger
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from mcp_bridge import MCPBridge
from llm_client import LLMClient
from sanitizer import Sanitizer
from world_model import WorldModel
from task_scheduling import TaskQueueManager
from task_reminder import TaskReminder
from dashboard_client import DashboardClient
from tool_executor import ToolExecutor
from tool_registry import get_tools
from system_prompt import build_system_message
from device_registry import DeviceRegistry
from wallet_bridge import WalletBridge
from event_store import init_db, EventWriter, HourlyAggregator

load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
LLM_API_URL = os.getenv("LLM_API_URL", "http://mock-llm:8000/v1")

REACT_MAX_ITERATIONS = 5
CYCLE_INTERVAL = 30       # Normal polling interval (seconds)
EVENT_BATCH_DELAY = 3     # Delay after event to batch multiple events (seconds)
MIN_CYCLE_INTERVAL = 25   # Minimum interval between cognitive cycles (seconds)
MAX_SPEAK_PER_CYCLE = 1   # Maximum speak calls per cognitive cycle
MAX_CONSECUTIVE_ERRORS = 1 # Stop cycle after this many consecutive tool errors


def _summarize_action(tool_name: str, args: dict) -> str:
    """Create a short summary of a tool call for action history."""
    if tool_name == "speak":
        return f"zone={args.get('zone', '?')}, msg={args.get('message', '')[:30]}"
    elif tool_name == "create_task":
        return f"title={args.get('title', '')}"
    elif tool_name == "get_zone_status":
        return f"zone={args.get('zone_id', '')}"
    elif tool_name == "get_device_status":
        return f"zone={args.get('zone_id', 'all')}"
    return str(args)[:50]


class Brain:
    def __init__(self):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.mcp = MCPBridge(self.client)
        self.sanitizer = Sanitizer()
        self.world_model = WorldModel()
        self.device_registry = DeviceRegistry()
        self.event_writer: EventWriter | None = None

        # Initialized in run() with shared session
        self.llm = None
        self.dashboard = None
        self.task_queue = None
        self.task_reminder = None
        self.tool_executor = None
        self.wallet_bridge = None

        # Event-driven trigger
        self._cycle_triggered = asyncio.Event()
        self._last_event_count: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

        # Action history for LLM context (Layer 5)
        self._action_history: list[dict] = []

    def on_connect(self, client, userdata, flags, rc, properties=None):
        logger.info(f"Connected to MQTT Broker with result code {rc}")
        client.subscribe("mcp/+/response/#")
        client.subscribe("office/#")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        if "mcp" in msg.topic and "response" in msg.topic:
            self.mcp.handle_response(msg.topic, payload)
            return

        # Dispatch to asyncio thread for thread-safe world_model access
        if self._loop:
            self._loop.call_soon_threadsafe(
                self._process_mqtt_message, msg.topic, payload
            )

    def _process_mqtt_message(self, topic: str, payload: dict):
        """Process MQTT message on the asyncio thread (thread-safe)."""
        self.world_model.update_from_mqtt(topic, payload)

        # Record sensor telemetry to event store
        if self.event_writer:
            parts = topic.split("/")
            # office/{zone}/sensor/{device_id}/{channel}
            if len(parts) >= 5 and parts[0] == "office" and parts[2] == "sensor":
                value = payload.get(parts[4]) or payload.get("value")
                if value is not None:
                    self.event_writer.record_sensor(
                        zone=parts[1],
                        channel=parts[4],
                        value=value,
                        device_id=parts[3],
                        topic=topic,
                    )

        # Forward heartbeat messages to DeviceRegistry and Wallet
        if "/heartbeat" in topic:
            parts = topic.split("/")
            # Extract device_id from topic (e.g., office/main/sensor/env_01/heartbeat)
            if len(parts) >= 4:
                device_id = parts[3]
                self.device_registry.update_from_heartbeat(device_id, payload)
                # Forward to Wallet service for reward distribution
                if self.wallet_bridge and self._loop:
                    asyncio.ensure_future(
                        self.wallet_bridge.forward_heartbeat(device_id, payload)
                    )
                    asyncio.ensure_future(
                        self.wallet_bridge.forward_children(device_id, payload)
                    )

        # Check if new events were generated -> trigger cycle
        current_event_counts = {
            zid: len(z.events) for zid, z in self.world_model.zones.items()
        }
        if current_event_counts != self._last_event_count:
            self._last_event_count = current_event_counts
            self._cycle_triggered.set()

    async def cognitive_cycle(self):
        """ReAct cognitive cycle: Think → Act → Observe → repeat."""
        cycle_start = time.time()
        total_tool_calls = 0

        # Process task queue
        if self.task_queue:
            await self.task_queue.process_queue()

        # Build context
        llm_context = self.world_model.get_llm_context()
        if not llm_context:
            return

        # Inject device network status
        device_summary = self.device_registry.get_status_summary()
        if device_summary:
            llm_context += f"\n\n### デバイスネットワーク状態\n{device_summary}"

        # Collect recent events (last 5 minutes)
        now = time.time()
        recent_events = []
        actionable_reports = []  # task_reports needing follow-up
        for zone_id, zone in self.world_model.zones.items():
            for event in zone.events:
                if now - event.timestamp < 300:
                    recent_events.append(f"[{zone_id}] {event.description}")
                    # Highlight task reports that need action
                    if event.event_type == "task_report":
                        status = event.data.get("report_status", "")
                        if status in ("needs_followup", "cannot_resolve"):
                            actionable_reports.append(
                                f"[{zone_id}] {event.description} (要対応)"
                            )

        # Fetch active tasks to prevent duplicates
        active_tasks = await self.dashboard.get_active_tasks()

        # Build messages
        system_msg = build_system_message()
        user_content = f"## 現在のオフィス状態\n{llm_context}"
        if recent_events:
            user_content += f"\n\n## 直近のイベント\n" + "\n".join(recent_events)
        if actionable_reports:
            user_content += "\n\n## ⚠ 対応が必要なタスク報告\n" + "\n".join(actionable_reports)
            user_content += "\n上記のタスク報告にはフォローアップが必要です。内容を確認し適切に対応してください。"

        # Inject active tasks so LLM knows what already exists
        if active_tasks:
            user_content += "\n\n## 現在のアクティブタスク（重複作成禁止）\n"
            for t in active_tasks[:10]:
                title = t.get("title", "")
                zone = t.get("zone", "")
                task_type = t.get("task_type", [])
                zone_str = f" [{zone}]" if zone else ""
                type_str = f" ({','.join(task_type)})" if task_type else ""
                user_content += f"- {title}{zone_str}{type_str}\n"
            user_content += "上記タスクと同じ目的のタスクを新規作成しないでください。"
        else:
            user_content += "\n\n## 現在のアクティブタスク\nなし"

        # Layer 5: Inject action history to prevent repetitive actions
        cutoff = now - 1800  # last 30 minutes
        recent_actions = [a for a in self._action_history if a["time"] > cutoff]
        if recent_actions:
            user_content += "\n\n## 直近のBrainアクション履歴（重複注意）\n"
            for a in recent_actions[-8:]:
                mins_ago = int((now - a["time"]) / 60)
                status = "✓" if a.get("success", True) else "✗失敗"
                user_content += f"- {mins_ago}分前: {a['tool']}({a.get('summary', '')}) [{status}]\n"
            failed = [a for a in recent_actions if not a.get("success", True)]
            if failed:
                user_content += "失敗したアクションと同じ操作を再試行しないでください。\n"
            user_content += "上記と同じアクションを短期間で繰り返さないでください。特にspeakは同じ内容を30分以内に再送しないこと。\n"

        user_msg = {"role": "user", "content": user_content}

        messages = [system_msg, user_msg]
        tools = get_tools()

        # Layer 3: ReAct loop guards
        tool_call_history = []  # (tool_name, args_hash) for duplicate detection
        speak_count = 0
        consecutive_errors = 0

        # ReAct loop
        iteration = 0
        for iteration in range(1, REACT_MAX_ITERATIONS + 1):
            logger.info(f"ReAct iteration {iteration}/{REACT_MAX_ITERATIONS}")

            response = await self.llm.chat(messages, tools)

            if response.error:
                logger.error(f"LLM error: {response.error}")
                break

            # No tool calls -> LLM decided no action needed
            if not response.tool_calls:
                if response.content:
                    logger.info(f"LLM (no action): {response.content[:200]}")
                break

            # Layer 3: Filter tool calls (duplicates, speak limit, task dedup)
            filtered_tool_calls = []
            for tc in response.tool_calls:
                name = tc["function"]["name"]
                args = tc["function"].get("arguments", {})
                call_key = (name, json.dumps(args, sort_keys=True))

                # Guard 1: Skip duplicate tool+args within this cycle
                if call_key in tool_call_history:
                    logger.warning(f"Skipping duplicate tool call: {name}")
                    continue

                # Guard 2: Limit speak calls per cycle
                if name == "speak":
                    if speak_count >= MAX_SPEAK_PER_CYCLE:
                        logger.warning(f"Skipping speak: max {MAX_SPEAK_PER_CYCLE}/cycle reached")
                        continue
                    speak_count += 1

                # Guard 4: Skip create_task if similar title exists in active tasks
                # or was recently attempted (prevents retry loop after rate limit)
                if name == "create_task":
                    proposed_title = args.get("title", "")
                    # Check against active tasks
                    if active_tasks and any(
                        proposed_title.lower() in t.get("title", "").lower()
                        or t.get("title", "").lower() in proposed_title.lower()
                        for t in active_tasks if proposed_title and t.get("title")
                    ):
                        logger.warning(f"Skipping create_task: similar active task exists for '{proposed_title}'")
                        continue
                    # Check against recent action history (last 30 min)
                    recent_creates = [
                        a for a in self._action_history
                        if a["tool"] == "create_task" and a["time"] > now - 1800
                    ]
                    if any(
                        proposed_title.lower() in a.get("summary", "").lower()
                        for a in recent_creates if proposed_title
                    ):
                        logger.warning(f"Skipping create_task: '{proposed_title}' was already attempted recently")
                        continue

                filtered_tool_calls.append(tc)
                tool_call_history.append(call_key)

            if not filtered_tool_calls:
                logger.info("All tool calls filtered out, ending cycle")
                break

            # Add assistant message with tool_calls to conversation
            assistant_msg = {"role": "assistant", "content": response.content or ""}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": json.dumps(tc["function"]["arguments"], ensure_ascii=False),
                    }
                }
                for tc in filtered_tool_calls
            ]
            messages.append(assistant_msg)

            # Execute each tool call
            total_tool_calls += len(filtered_tool_calls)
            cycle_aborted = False
            for tc in filtered_tool_calls:
                tool_name = tc["function"]["name"]
                arguments = tc["function"]["arguments"]
                tool_call_id = tc["id"]

                logger.info(f"Executing tool: {tool_name} with {arguments}")

                result = await self.tool_executor.execute(tool_name, arguments)

                if result["success"]:
                    logger.info(f"Tool result: {result['result'][:200]}")
                    consecutive_errors = 0

                    # Suppress alerts after successful environment task creation
                    # so the same condition doesn't trigger duplicate tasks
                    # while the physical environment slowly changes.
                    if tool_name == "create_task":
                        self._suppress_alert_for_task(arguments)
                else:
                    logger.warning(f"Tool failed: {result['error']}")
                    consecutive_errors += 1

                # Layer 5: Record action in history
                self._action_history.append({
                    "time": time.time(),
                    "tool": tool_name,
                    "summary": _summarize_action(tool_name, arguments),
                    "success": result.get("success", True),
                })

                # Add tool result to conversation
                result_content = result.get("result") or result.get("error", "")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": str(result_content),
                })

                # Guard 3: Stop on consecutive errors
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.warning(f"Stopping cycle: {consecutive_errors} consecutive error(s)")
                    cycle_aborted = True
                    break

            if cycle_aborted:
                break

            # Continue loop - LLM will see tool results and decide next action

        # Record decision to event store
        elapsed = time.time() - cycle_start
        if self.event_writer and (total_tool_calls > 0 or iteration > 0):
            # Collect tool call summaries for logging
            cycle_tool_calls = [
                {"tool": a["tool"], "summary": a.get("summary", ""), "success": a.get("success", True)}
                for a in self._action_history
                if a["time"] >= cycle_start
            ]
            # Snapshot recent events that triggered this cycle
            trigger = [
                {"zone": zid, "event": e.event_type, "severity": e.severity}
                for zid, z in self.world_model.zones.items()
                for e in z.events
                if cycle_start - e.timestamp < 60  # events in the last minute
            ][:20]
            self.event_writer.record_decision(
                cycle_duration=elapsed,
                iterations=iteration,
                total_tool_calls=total_tool_calls,
                trigger_events=trigger,
                tool_calls=cycle_tool_calls,
            )

        # Layer 5: Prune old action history (older than 2 hours)
        cutoff_2h = time.time() - 7200
        self._action_history = [a for a in self._action_history if a["time"] > cutoff_2h]

        # Record utility_score boosts for devices in zones where actions were taken
        recent_actions = [
            a for a in self._action_history
            if a["time"] > cycle_start and a.get("success", True)
        ]
        for action in recent_actions:
            summary = action.get("summary", "")
            zone = None
            # Extract zone from summary (e.g., "zone=main, ...")
            if "zone=" in summary:
                zone = summary.split("zone=")[1].split(",")[0].strip()
            elif "title=" in summary:
                # create_task doesn't always have zone in summary; skip
                pass
            if zone:
                action_type = "task" if action["tool"] == "create_task" else "decision"
                self.device_registry.record_zone_action(zone, action_type)

        logger.info(
            f"Cycle complete: iterations={iteration}, tool_calls={total_tool_calls}, elapsed={elapsed:.1f}s"
        )

    # Mapping from task_types keywords to alert suppression types
    _TASK_TYPE_TO_ALERT = {
        "environment": {
            "温度": ["high_temp", "low_temp"],
            "室温": ["high_temp", "low_temp"],
            "暑": ["high_temp"],
            "寒": ["low_temp"],
            "冷": ["high_temp"],     # 冷房 → suppress high_temp
            "暖": ["low_temp"],      # 暖房 → suppress low_temp
            "co2": ["high_co2"],
            "換気": ["high_co2"],
            "湿度": ["high_humidity", "low_humidity"],
            "加湿": ["low_humidity"],
            "除湿": ["high_humidity"],
        }
    }

    def _suppress_alert_for_task(self, task_args: dict):
        """After a successful create_task, suppress related alerts."""
        zone = task_args.get("zone") or task_args.get("zone_id")
        task_types = task_args.get("task_types", "")
        title = task_args.get("title", "")
        description = task_args.get("description", "")
        text = f"{title} {description} {task_types}".lower()

        if "environment" not in text and "urgent" not in text:
            return  # Not an environment task

        # Determine which zones to suppress (fall back to all zones)
        target_zones = [zone] if zone else list(self.world_model.zones.keys())

        suppressed = set()
        for keyword, alert_types in self._TASK_TYPE_TO_ALERT.get("environment", {}).items():
            if keyword in text:
                for z in target_zones:
                    for at in alert_types:
                        if (z, at) not in suppressed:
                            self.world_model.suppress_alert(z, at)
                            suppressed.add((z, at))

    async def _utility_decay_loop(self):
        """Periodically decay utility_scores for idle devices (every hour)."""
        while True:
            await asyncio.sleep(3600)
            try:
                self.device_registry.decay_utility_scores()
                logger.debug("Utility score decay applied")
            except Exception as e:
                logger.error(f"Utility decay error: {e}")

    async def run(self):
        self._loop = asyncio.get_running_loop()
        logger.info(f"Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_user = os.getenv("MQTT_USER")
        mqtt_pass = os.getenv("MQTT_PASS")
        if mqtt_user:
            self.client.username_pw_set(mqtt_user, mqtt_pass)
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}")
            return

        # Initialize event store (PostgreSQL)
        try:
            engine = await init_db()
            if engine:
                self.event_writer = EventWriter(engine)
                self.world_model.event_writer = self.event_writer
                asyncio.create_task(self.event_writer.start())
                aggregator = HourlyAggregator(engine)
                asyncio.create_task(aggregator.start())
                logger.info("Event store and aggregator started")
            else:
                logger.warning("Event store disabled (no DATABASE_URL)")
        except Exception as e:
            logger.error(f"Event store init failed (non-fatal): {e}")

        # Shared HTTP session for all components (Layer 2)
        async with aiohttp.ClientSession() as session:
            # Initialize components with shared session
            self.llm = LLMClient(api_url=LLM_API_URL, session=session)
            self.dashboard = DashboardClient(session=session)
            self.task_reminder = TaskReminder(session=session)
            self.task_queue = TaskQueueManager(self.world_model, self.dashboard)
            self.tool_executor = ToolExecutor(
                sanitizer=self.sanitizer,
                mcp_bridge=self.mcp,
                dashboard_client=self.dashboard,
                world_model=self.world_model,
                task_queue=self.task_queue,
                session=session,
                device_registry=self.device_registry,
            )
            self.wallet_bridge = WalletBridge(session, self.device_registry)
            logger.info("All components initialized with shared HTTP session")

            # Start reminder service
            asyncio.create_task(self.task_reminder.run_periodic_check())
            logger.info("TaskReminder service started")

            # Start periodic utility_score decay (every hour)
            asyncio.create_task(self._utility_decay_loop())

            logger.info("Brain is running (ReAct mode)...")
            last_cycle_time = 0.0

            while True:
                # Wait for event trigger or timeout
                try:
                    await asyncio.wait_for(
                        self._cycle_triggered.wait(),
                        timeout=CYCLE_INTERVAL,
                    )
                    # Event triggered - wait briefly to batch multiple events
                    self._cycle_triggered.clear()
                    await asyncio.sleep(EVENT_BATCH_DELAY)
                except asyncio.TimeoutError:
                    pass  # Normal polling interval reached

                # Layer 4: Rate limit — enforce minimum interval between cycles
                elapsed = time.time() - last_cycle_time
                if elapsed < MIN_CYCLE_INTERVAL:
                    await asyncio.sleep(MIN_CYCLE_INTERVAL - elapsed)

                try:
                    await self.cognitive_cycle()
                    last_cycle_time = time.time()
                except Exception as e:
                    logger.error(f"Cognitive cycle error: {e}")


if __name__ == "__main__":
    brain = Brain()
    try:
        asyncio.run(brain.run())
    except KeyboardInterrupt:
        pass
