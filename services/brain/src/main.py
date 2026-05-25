"""
HEMS Brain — LLM + Rule-based dual-mode cognitive engine.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import aiohttp
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from brain_chat_server import ChatServerMixin
from brain_cognitive import CognitiveCycleMixin
from brain_constants import BIOMETRIC_ENABLED, HA_ENABLED, SWITCHBOT_ENABLED
from brain_loops import BackgroundLoopsMixin
from brain_mqtt import MqttSyncMixin
from brain_runtime import BrainRuntimeMixin
from brain_startup import BrainStartupMixin
from character_loader import load_character
from device_registry import DeviceRegistry
from low_power_mode import PowerModeManager
from mcp_bridge import MCPBridge
from rule_engine import RuleEngine
from sanitizer import Sanitizer
from schedule_learner import ScheduleLearner
from sunrise_alarm import SunriseAlarm
from world_model import WorldModel

if TYPE_CHECKING:
    from ambient_speaker import AmbientSpeaker
    from annotator import RulePromoter, ShoppingClassifier
    from automation_engine import AutomationEngine
    from boot_load_manager import BootLoadManager
    from device_dispatcher import DeviceDispatcher
    from event_automation import EventAutomation
    from event_store import EventWriter
    from llm_router import LLMRouter
    from scene_executor import SceneExecutor
    from timeline import TimelineGenerator

load_dotenv()


class Brain(
    MqttSyncMixin,
    CognitiveCycleMixin,
    ChatServerMixin,
    BackgroundLoopsMixin,
    BrainRuntimeMixin,
    BrainStartupMixin,
):
    def __init__(self):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.mcp = MCPBridge(self.client)
        self.sanitizer = Sanitizer()
        self.world_model = WorldModel()
        self.device_registry = DeviceRegistry()
        self.event_writer: EventWriter | None = None
        self._recent_efficacy_verdicts: list[dict] = []
        self.character = load_character()
        self.schedule_learner = ScheduleLearner() if (HA_ENABLED or BIOMETRIC_ENABLED or SWITCHBOT_ENABLED) else None
        self.rule_engine = RuleEngine(
            schedule_learner=self.schedule_learner,
            mqtt_publisher=self._publish_mqtt,
        )
        self.power_mode_manager = PowerModeManager()

        self.llm = None
        self.llm_router: LLMRouter | None = None
        self.boot_load_manager: BootLoadManager | None = None
        self.sunrise_alarm: SunriseAlarm | None = SunriseAlarm() if os.getenv("SUNRISE_ALARM_DEVICE") else None
        self.persona_rewriter = None
        self.dashboard = None
        self.task_queue = None
        self.task_reminder = None
        self.tool_executor = None
        self._session: aiohttp.ClientSession | None = None

        self.ambient_speaker: AmbientSpeaker | None = None
        self.event_automation: EventAutomation | None = None
        self.timeline_generator: TimelineGenerator | None = None
        self._scheduled_wake_fired_date: str | None = None
        self.device_dispatcher: DeviceDispatcher | None = None
        self.scene_executor: SceneExecutor | None = None
        self.automation_engine: AutomationEngine | None = None
        self.shopping_classifier: ShoppingClassifier | None = None
        self.event_classifier = None  # wired in brain_startup._wire_runtime_components
        self._rule_promoter: RulePromoter | None = None
        self._ack_learner = None
        self._daily_maintenance_date: str | None = None
        # Bridge SLA tracking state (populated lazily by _track_bridge_transitions)
        self._bridge_state_cache: dict[str, bool] = {}
        self._bridge_disconnect_history: dict[str, list[float]] = {}
        self._bridge_outage_alert_sent: dict[str, float] = {}
        self._heartbeat_debounce: dict[str, float] = {}
        self._cached_devices: list[dict] = []
        self._cached_devices_at: float = 0.0
        self._device_zone_map: dict[str, str] = {}
        self._z2m_bridge_devices_pending: list[dict] | None = None

        self._cycle_triggered = asyncio.Event()
        self._last_event_count: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._action_history: list[dict] = []
        self._last_cycle_summary: dict | None = None
        self._schedule_save_counter: int = 0
        self._timeline_regen_task: asyncio.Task | None = None

    _TASK_ALERT_KEYWORDS: dict[str, list[str]] = {
        "温度": ["temp_high", "temp_low"],
        "室温": ["temp_high", "temp_low"],
        "暑": ["temp_high"],
        "冷": ["temp_high"],
        "寒": ["temp_low"],
        "暖": ["temp_low"],
        "co2": ["co2_high", "co2_critical"],
        "換気": ["co2_high", "co2_critical"],
        "二酸化炭素": ["co2_high", "co2_critical"],
        "湿度": ["humidity_high", "humidity_low"],
        "加湿": ["humidity_low"],
        "除湿": ["humidity_high"],
    }

    async def run(self):
        self._loop = asyncio.get_running_loop()
        if not await self._connect_mqtt_client():
            return

        await self._start_event_store()
        async with aiohttp.ClientSession() as session:
            await self._wire_runtime_components(session)
            self._log_integrations()
            await self._start_timeline_and_reminders()
            await self._finish_bootstrap()
            await self._run_cognitive_loop()


if __name__ == "__main__":
    brain = Brain()
    try:
        asyncio.run(brain.run())
    except KeyboardInterrupt:
        pass
