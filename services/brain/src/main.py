"""
HEMS Brain — LLM + Rule-based dual-mode cognitive engine.
Forked from SOMS Brain with character system, GPU load detection,
and simplified for single-user home use.
"""
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
from character_loader import load_character, reload_character
from rule_engine import RuleEngine
from event_store import init_db, EventWriter, HourlyAggregator

load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
LLM_API_URL = os.getenv("LLM_API_URL", "http://mock-llm:8000/v1")

REACT_MAX_ITERATIONS = 5
CYCLE_INTERVAL = 30
EVENT_BATCH_DELAY = 3
MIN_CYCLE_INTERVAL = 25
MAX_SPEAK_PER_CYCLE = 1
MAX_CONSECUTIVE_ERRORS = 1


def _summarize_action(tool_name: str, args: dict) -> str:
    if tool_name == "speak":
        return f"zone={args.get('zone', '?')}, msg={args.get('message', '')[:30]}"
    elif tool_name == "create_task":
        return f"title={args.get('title', '')}"
    elif tool_name == "get_zone_status":
        return f"zone={args.get('zone_id', '')}"
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
        self.character = load_character()
        self.rule_engine = RuleEngine()

        self.llm = None
        self.dashboard = None
        self.task_queue = None
        self.task_reminder = None
        self.tool_executor = None

        self._cycle_triggered = asyncio.Event()
        self._last_event_count: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._action_history: list[dict] = []

    def on_connect(self, client, userdata, flags, rc, properties=None):
        logger.info(f"Connected to MQTT Broker (rc={rc})")
        client.subscribe("mcp/+/response/#")
        client.subscribe("office/#")
        client.subscribe("hems/#")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        if "mcp" in msg.topic and "response" in msg.topic:
            self.mcp.handle_response(msg.topic, payload)
            return

        if msg.topic == "hems/brain/reload-character":
            logger.info("Character reload command received")
            self.character = reload_character()
            return

        if self._loop:
            self._loop.call_soon_threadsafe(self._process_mqtt, msg.topic, payload)

    def _process_mqtt(self, topic: str, payload: dict):
        self.world_model.update_from_mqtt(topic, payload)

        if self.event_writer:
            parts = topic.split("/")
            if len(parts) >= 5 and parts[0] == "office" and parts[2] == "sensor":
                value = payload.get(parts[4]) or payload.get("value")
                if value is not None:
                    self.event_writer.record_sensor(
                        zone=parts[1], channel=parts[4], value=value,
                        device_id=parts[3], topic=topic,
                    )

        if "/heartbeat" in topic:
            parts = topic.split("/")
            if len(parts) >= 4:
                self.device_registry.update_from_heartbeat(parts[3], payload)

        current = {zid: len(z.events) for zid, z in self.world_model.zones.items()}
        if current != self._last_event_count:
            self._last_event_count = current
            self._cycle_triggered.set()

    async def cognitive_cycle(self):
        cycle_start = time.time()
        total_tool_calls = 0

        if self.task_queue:
            await self.task_queue.process_queue()

        # Rule-based fallback when GPU is busy
        if self.rule_engine.should_use_rules():
            logger.info("GPU load high — rule-based mode")
            for action in self.rule_engine.evaluate(self.world_model):
                result = await self.tool_executor.execute(action["tool"], action["args"])
                total_tool_calls += 1
                self._action_history.append({
                    "time": time.time(), "tool": action["tool"],
                    "summary": _summarize_action(action["tool"], action["args"]),
                    "success": result.get("success", True),
                })
            await self.dashboard.push_zone_snapshot(self.world_model)
            return

        llm_context = self.world_model.get_llm_context()
        if not llm_context:
            return

        device_summary = self.device_registry.get_status_summary()
        if device_summary:
            llm_context += f"\n\n### デバイスネットワーク状態\n{device_summary}"

        now = time.time()
        recent_events = []
        for zone_id, zone in self.world_model.zones.items():
            for event in zone.events:
                if now - event.timestamp < 300:
                    recent_events.append(f"[{zone_id}] {event.description}")

        active_tasks = await self.dashboard.get_active_tasks()

        system_msg = build_system_message(self.character)
        user_content = f"## 現在の自宅状態\n{llm_context}"
        if recent_events:
            user_content += "\n\n## 直近のイベント\n" + "\n".join(recent_events)

        if active_tasks:
            user_content += "\n\n## 現在のアクティブタスク（重複作成禁止）\n"
            for t in active_tasks[:10]:
                user_content += f"- {t.get('title', '')}\n"

        # Inject action history
        cutoff = now - 1800
        recent_actions = [a for a in self._action_history if a["time"] > cutoff]
        if recent_actions:
            user_content += "\n\n## 直近のアクション履歴\n"
            for a in recent_actions[-8:]:
                mins_ago = int((now - a["time"]) / 60)
                user_content += f"- {mins_ago}分前: {a['tool']}({a.get('summary', '')})\n"

        messages = [system_msg, {"role": "user", "content": user_content}]
        tools = get_tools()

        tool_call_history = []
        speak_count = 0
        consecutive_errors = 0
        iteration = 0

        for iteration in range(1, REACT_MAX_ITERATIONS + 1):
            response = await self.llm.chat(messages, tools)
            if response.error or not response.tool_calls:
                break

            filtered = []
            for tc in response.tool_calls:
                name = tc["function"]["name"]
                args = tc["function"].get("arguments", {})
                call_key = (name, json.dumps(args, sort_keys=True))
                if call_key in tool_call_history:
                    continue
                if name == "speak" and speak_count >= MAX_SPEAK_PER_CYCLE:
                    continue
                if name == "speak":
                    speak_count += 1
                filtered.append(tc)
                tool_call_history.append(call_key)

            if not filtered:
                break

            assistant_msg = {"role": "assistant", "content": response.content or ""}
            assistant_msg["tool_calls"] = [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["function"]["name"],
                              "arguments": json.dumps(tc["function"]["arguments"], ensure_ascii=False)}}
                for tc in filtered
            ]
            messages.append(assistant_msg)

            total_tool_calls += len(filtered)
            for tc in filtered:
                tool_name = tc["function"]["name"]
                arguments = tc["function"]["arguments"]
                result = await self.tool_executor.execute(tool_name, arguments)

                self._action_history.append({
                    "time": time.time(), "tool": tool_name,
                    "summary": _summarize_action(tool_name, arguments),
                    "success": result.get("success", True),
                })

                messages.append({
                    "role": "tool", "tool_call_id": tc["id"],
                    "content": str(result.get("result") or result.get("error", "")),
                })

                if not result["success"]:
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        break
                else:
                    consecutive_errors = 0

        # Record to event store
        elapsed = time.time() - cycle_start
        if self.event_writer and total_tool_calls > 0:
            self.event_writer.record_decision(
                cycle_duration=elapsed, iterations=iteration,
                total_tool_calls=total_tool_calls,
                trigger_events=[], tool_calls=[
                    {"tool": a["tool"], "summary": a.get("summary", "")}
                    for a in self._action_history if a["time"] >= cycle_start
                ],
            )

        # Prune old history
        self._action_history = [a for a in self._action_history if a["time"] > time.time() - 7200]

        # Push zone sensor snapshot to backend for frontend
        await self.dashboard.push_zone_snapshot(self.world_model)

        logger.info(f"Cycle: iter={iteration}, tools={total_tool_calls}, elapsed={elapsed:.1f}s")

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
            logger.error(f"MQTT connect failed: {e}")
            return

        try:
            engine = await init_db()
            if engine:
                self.event_writer = EventWriter(engine)
                self.world_model.event_writer = self.event_writer
                asyncio.create_task(self.event_writer.start())
                asyncio.create_task(HourlyAggregator(engine).start())
                logger.info("Event store started")
        except Exception as e:
            logger.error(f"Event store init failed (non-fatal): {e}")

        async with aiohttp.ClientSession() as session:
            self.llm = LLMClient(api_url=LLM_API_URL, session=session)
            self.dashboard = DashboardClient(session=session)
            self.task_reminder = TaskReminder(session=session)
            self.task_queue = TaskQueueManager(self.world_model, self.dashboard)
            self.tool_executor = ToolExecutor(
                sanitizer=self.sanitizer, mcp_bridge=self.mcp,
                dashboard_client=self.dashboard, world_model=self.world_model,
                task_queue=self.task_queue, session=session,
                device_registry=self.device_registry,
            )
            asyncio.create_task(self.task_reminder.run_periodic_check())
            logger.info("HEMS Brain running (ReAct mode)...")

            last_cycle = 0.0
            while True:
                try:
                    await asyncio.wait_for(self._cycle_triggered.wait(), timeout=CYCLE_INTERVAL)
                    self._cycle_triggered.clear()
                    await asyncio.sleep(EVENT_BATCH_DELAY)
                except asyncio.TimeoutError:
                    pass

                if time.time() - last_cycle < MIN_CYCLE_INTERVAL:
                    await asyncio.sleep(MIN_CYCLE_INTERVAL - (time.time() - last_cycle))

                try:
                    await self.cognitive_cycle()
                    last_cycle = time.time()
                except Exception as e:
                    logger.error(f"Cognitive cycle error: {e}")


if __name__ == "__main__":
    brain = Brain()
    try:
        asyncio.run(brain.run())
    except KeyboardInterrupt:
        pass
