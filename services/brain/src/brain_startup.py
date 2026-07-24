import asyncio
import os
from typing import Any

from aiohttp import web as aio_web
from loguru import logger

from adaptive_thresholds import (
    AdaptiveThresholdManager,
    ThresholdAdjuster,
    ThresholdClient,
)
from ambient_speaker import AmbientSpeaker
from annotator import ClassifierCache, EventClassifier, RulePromoter, ShoppingClassifier
from approval.client import ApprovalClient
from approval.gate import ApprovalGate
from approval.rollback_executor import RollbackExecutor
from automation_engine import AutomationEngine
from boot_load_manager import BootLoadManager
from brain_constants import (
    BACKEND_URL,
    BIOMETRIC_BRIDGE_URL,
    BIOMETRIC_ENABLED,
    BOOT_LOAD_ENABLED,
    CHAT_SERVER_PORT,
    GAS_BRIDGE_URL,
    GAS_ENABLED,
    HA_BRIDGE_URL,
    HA_ENABLED,
    KNOWLEDGE_BRIDGE_URL,
    KNOWLEDGE_ENABLED,
    LLM_API_URL,
    MQTT_BROKER,
    MQTT_PORT,
    NEWS_BRIDGE_URL,
    NEWS_ENABLED,
    OBSIDIAN_BRIDGE_URL,
    OBSIDIAN_ENABLED,
    OPENCLAW_BRIDGE_URL,
    OPENCLAW_ENABLED,
    PERCEPTION_BRIDGE_URL,
    PERCEPTION_ENABLED,
    SWITCHBOT_BRIDGE_URL,
    SWITCHBOT_ENABLED,
)
from dashboard_client import DashboardClient
from device_dispatcher import DeviceDispatcher
from event_automation import EventAutomation
from event_store import EventWriter, HourlyAggregator, init_db
from feedback import FeedbackCollector, ImplicitFeedbackDetector, OutcomeRewardCalculator, TrajectoryRecorder
from llm_client import LLMClient
from llm_router import LLMRouter
from persona_rewriter import PersonaRewriter
from rules.config import AdaptiveRuleThresholds, load_rule_thresholds
from scene_executor import SceneExecutor
from task_reminder import TaskReminder
from task_scheduling import TaskQueueManager
from timeline import TimelineGenerator
from tool_executor import ToolExecutor


class BrainStartupMixin:
    async def _connect_mqtt_client(self) -> bool:
        logger.info(f"Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_user = os.getenv("MQTT_USER")
        mqtt_pass = os.getenv("MQTT_PASS")
        if mqtt_user:
            self.client.username_pw_set(mqtt_user, mqtt_pass)
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"MQTT connect failed: {e}")
            return False

    async def _start_event_store(self) -> None:
        try:
            engine = await init_db()
            if engine:
                self.event_writer = EventWriter(engine)
                self.world_model.event_writer = self.event_writer
                asyncio.create_task(self.event_writer.start())
                asyncio.create_task(HourlyAggregator(engine).start())
                asyncio.create_task(self._efficacy_eval_loop())
                logger.info("Event store started")
        except Exception as e:
            logger.error(f"Event store init failed (non-fatal): {e}")

    async def _wire_runtime_components(self, session) -> None:
        self._session = session
        self.llm = LLMClient(api_url=LLM_API_URL, session=session)
        self.llm_router = LLMRouter(self.llm, session=session)
        self.boot_load_manager = BootLoadManager() if BOOT_LOAD_ENABLED else None
        self.persona_rewriter = PersonaRewriter(self.character, self.llm)
        self.dashboard = DashboardClient(session=session)

        classifier_cache = ClassifierCache(session=session, backend_url=BACKEND_URL)
        self.shopping_classifier = ShoppingClassifier(
            session=session,
            backend_url=BACKEND_URL,
            cache=classifier_cache,
            llm_router=self.llm_router,
        )
        self.event_classifier = EventClassifier(llm_router=self.llm_router, cache=classifier_cache)
        self._rule_promoter = RulePromoter(
            session=session,
            backend_url=BACKEND_URL,
            obsidian_url=OBSIDIAN_BRIDGE_URL,
        )

        from voice_capsule.ack_learner import AckLearner

        self._ack_learner = AckLearner(session=session, backend_url=BACKEND_URL)
        if self.boot_load_manager is not None:
            self.boot_load_manager.configure_capsule(
                persona_rewriter=self.persona_rewriter,
                mqtt_client=self.client,
                character_version=os.getenv("CHARACTER_VERSION", os.getenv("CHARACTER", "default")),
                schedule_learner=self.schedule_learner,
                event_classifier=self.event_classifier,
            )

        self.task_reminder = TaskReminder(session=session)
        self.task_queue = TaskQueueManager(self.world_model, self.dashboard)
        self.device_dispatcher = DeviceDispatcher(session=session, mqtt_client=self.client, mcp_bridge=self.mcp)
        self.rule_engine.device_dispatcher = self.device_dispatcher
        self.scene_executor = SceneExecutor(
            device_dispatcher=self.device_dispatcher,
            dashboard_client=self.dashboard,
        )
        self.approval_client = ApprovalClient(backend_url=BACKEND_URL, session=session)
        self.rollback_executor = RollbackExecutor(
            client=self.approval_client,
            executor=self.scene_executor.execute,
        )
        self.approval_gate = ApprovalGate(
            client=self.approval_client,
            executor=self.scene_executor.execute,
            state_lookup=self._lookup_device_state,
            event_writer=self.event_writer,
            rollback_executor=self.rollback_executor,
        )

        # Phase 2 adaptive thresholds: wrap static thresholds and load approved offsets.
        self.threshold_client = ThresholdClient(backend_url=BACKEND_URL, session=session)
        base_thresholds = load_rule_thresholds()
        self.adaptive_thresholds = AdaptiveRuleThresholds(base_thresholds)
        try:
            adjustments = await self.threshold_client.list_adjustments()
            for adj in adjustments:
                metric_key = adj.get("metric_key")
                offset = adj.get("offset", 0.0)
                if metric_key:
                    self.adaptive_thresholds.set_offset(metric_key, float(offset))
        except Exception as e:
            logger.warning(f"Failed to load threshold adjustments: {e}")

        self.adaptive_threshold_manager = AdaptiveThresholdManager(
            thresholds=self.adaptive_thresholds.base,
            event_writer=self.event_writer,
            backend_client=self.threshold_client,
        )
        self.threshold_adjuster = ThresholdAdjuster()

        # Replace WorldModel/RuleEngine thresholds with the dynamic wrapper.
        self.world_model.thresholds = self.adaptive_thresholds
        self.world_model.adaptive_manager = self.adaptive_threshold_manager
        self.rule_engine.thresholds = self.adaptive_thresholds

        self.feedback_collector = FeedbackCollector(event_writer=self.event_writer)
        self.implicit_detector = ImplicitFeedbackDetector(collector=self.feedback_collector)
        self.outcome_reward = OutcomeRewardCalculator()
        self.trajectory_recorder = TrajectoryRecorder(event_writer=self.event_writer)
        self.automation_engine = AutomationEngine(
            dispatcher=self.device_dispatcher,
            scene_executor=self.scene_executor,
            dashboard_client=self.dashboard,
            llm_client=self.llm,
            world_model=self.world_model,
            sanitizer=self.sanitizer,
            approval_gate=self.approval_gate,
            implicit_detector=self.implicit_detector,
        )
        self.tool_executor = ToolExecutor(
            sanitizer=self.sanitizer,
            dashboard_client=self.dashboard,
            world_model=self.world_model,
            task_queue=self.task_queue,
            session=session,
            device_registry=self.device_registry,
            device_dispatcher=self.device_dispatcher,
            scene_executor=self.scene_executor,
            persona_rewriter=self.persona_rewriter,
            power_mode_manager=self.power_mode_manager,
            event_writer=self.event_writer,
        )
        self.ambient_speaker = AmbientSpeaker(
            llm_client=self.llm,
            world_model=self.world_model,
            character=self.character,
            persona_rewriter=self.persona_rewriter,
        )
        self.event_automation = EventAutomation(
            tool_executor=self.tool_executor,
            world_model=self.world_model,
            llm_client=self.llm,
            character=self.character,
            boot_load_manager=self.boot_load_manager,
        )
        self.event_automation.set_session(session)
        self.timeline_generator = TimelineGenerator(
            world_model=self.world_model,
            schedule_learner=self.schedule_learner,
            session=session,
        )
        logger.info("Timeline generator initialized")

    async def _lookup_device_state(self, device_id: str) -> dict[str, Any] | None:
        """Return current device state dict for ApprovalGate snapshots.

        Looks up the device in the world model and device registry, falling back
        to the backend device dispatcher for the authoritative last_state.
        """
        # WorldModel zone devices (edge sensors)
        for zone in self.world_model.zones.values():
            dev = zone.devices.get(device_id)
            if dev is not None:
                return {"last_state": dev.state or {}}

        # DeviceRegistry metadata/network state
        dev = self.device_registry.get_device(device_id)
        if dev is not None:
            return {"last_state": {"state": dev.state, **dev.to_dict()}}

        # Backend dispatcher has the authoritative last_state for actuators
        if self.device_dispatcher is not None:
            device = await self.device_dispatcher.lookup(device_id)
            if device is not None:
                return {"last_state": device.get("last_state", {})}

        return None

    def _log_integrations(self) -> None:
        if NEWS_ENABLED:
            logger.info(f"News integration enabled (bridge={NEWS_BRIDGE_URL})")
        else:
            logger.info("News integration disabled (NEWS_BRIDGE_URL not set); event automation still active")
        if OPENCLAW_ENABLED:
            logger.info(f"OpenClaw integration enabled (bridge={OPENCLAW_BRIDGE_URL})")
        else:
            logger.info("OpenClaw integration disabled (OPENCLAW_BRIDGE_URL/LOCALCRAW_BRIDGE_URL not set)")
        if OBSIDIAN_ENABLED:
            logger.info(f"Obsidian integration enabled (bridge={OBSIDIAN_BRIDGE_URL})")
        else:
            logger.info("Obsidian integration disabled (OBSIDIAN_BRIDGE_URL not set)")
        if GAS_ENABLED:
            logger.info(f"GAS integration enabled (bridge={GAS_BRIDGE_URL})")
        else:
            logger.info("GAS integration disabled (GAS_BRIDGE_URL not set)")
        if HA_ENABLED:
            logger.info(f"Home Assistant integration enabled (bridge={HA_BRIDGE_URL})")
        else:
            logger.info("Home Assistant integration disabled (HA_BRIDGE_URL not set)")
        if BIOMETRIC_ENABLED:
            logger.info(f"Biometric integration enabled (bridge={BIOMETRIC_BRIDGE_URL})")
        else:
            logger.info("Biometric integration disabled (BIOMETRIC_BRIDGE_URL not set)")
        if PERCEPTION_ENABLED:
            logger.info(f"Perception integration enabled (bridge={PERCEPTION_BRIDGE_URL})")
        else:
            logger.info("Perception integration disabled (PERCEPTION_BRIDGE_URL not set)")
        if SWITCHBOT_ENABLED:
            logger.info(f"SwitchBot integration enabled (bridge={SWITCHBOT_BRIDGE_URL})")
        else:
            logger.info("SwitchBot integration disabled (SWITCHBOT_BRIDGE_URL not set)")
        if KNOWLEDGE_ENABLED:
            logger.info(f"Knowledge integration enabled (bridge={KNOWLEDGE_BRIDGE_URL})")
        else:
            logger.info("Knowledge integration disabled (KNOWLEDGE_BRIDGE_URL not set)")

    async def _start_timeline_and_reminders(self) -> None:
        async def _initial_timeline_gen():
            try:
                await asyncio.sleep(3)
                await self.timeline_generator.generate_week()
            except Exception as e:
                logger.warning(f"Initial timeline generation error: {e}")

        asyncio.create_task(_initial_timeline_gen())
        asyncio.create_task(self.task_reminder.run_periodic_check())

    async def _start_chat_http_server(self) -> None:
        from brain_chat_server import brain_auth_middleware

        chat_app = aio_web.Application(middlewares=[brain_auth_middleware])
        chat_app.router.add_post("/chat", self._handle_chat)
        chat_app.router.add_get("/health", self._chat_health)
        chat_app.router.add_post("/devices/control", self._handle_device_control)
        chat_app.router.add_post("/devices/zigbee/permit_join", self._handle_zigbee_permit_join)
        chat_app.router.add_post("/scenes/execute", self._handle_scene_execute)
        chat_app.router.add_post("/automations/evaluate", self._handle_automation_evaluate)
        chat_runner = aio_web.AppRunner(chat_app)
        await chat_runner.setup()
        chat_site = aio_web.TCPSite(chat_runner, "0.0.0.0", CHAT_SERVER_PORT)
        await chat_site.start()
        logger.info(f"Brain chat server started on :{CHAT_SERVER_PORT}")

    async def _start_automation_engine_if_enabled(self) -> None:
        if self.automation_engine is not None:
            if os.getenv("AUTOMATION_ENGINE_ENABLED", "true").lower() not in ("0", "false", "no"):
                await self.automation_engine.start()

    async def _finish_bootstrap(self) -> None:
        self._load_schedule_state()
        await self._start_chat_http_server()
        await self._start_automation_engine_if_enabled()
        logger.info("HEMS Brain running (ReAct mode)...")

        if self._z2m_bridge_devices_pending is not None:
            self._annotate_z2m_devices(self._z2m_bridge_devices_pending)
            self._z2m_bridge_devices_pending = None

        await self._get_cached_devices(max_age=0)
