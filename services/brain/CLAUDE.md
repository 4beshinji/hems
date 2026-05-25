# services/brain/

Brain service — ReAct cognitive loop, plugin registry, world model, chat server, event automation.

Extends the parent `hems/CLAUDE.md` (entry, build/run, MQTT topics, ports). Read that first if you haven't.

## Brain Service

- ReAct cognitive loop (30s cycle, max 5 iterations)
- Dual mode: LLM + rule-based fallback (GPU load > threshold, low-power mode, VLM heavy-model swap)
- Character personality 2-stage separation: Stage 1 thinking on raw model, Stage 2 output via PersonaRewriter
- Event store data mart (SOMS-compatible schema, 730d retention)
- Alert suppression: prevents duplicate tasks while environment slowly responds
  (e.g., AC cooling after task created — 30min for temp, 10min for CO2)
- Ambient Speaker: generates natural one-line speech every 5 minutes based on sensor data
- Tri-domain world model: Physical Space (zones, smart home, weather), Digital Space (PC, services, GAS, knowledge, shopping, news), User State (biometrics, screen time, schedule)
- Subsystems wired in two stages: always-on core in `main.py` (`Brain.__init__`), async startup in `brain_startup.py` (`_wire_runtime_components`, called from `Brain.run()`):
  - **PowerModeManager** (`low_power_mode.py`): normal/sleep/away mode + LLM rate limiting
  - **LLMRouter** (`llm_router.py`): light/heavy model routing
  - **BootLoadManager** (`boot_load_manager.py`, `BOOT_LOAD_ENABLED=true` default): pre-wake heavy model briefing pre-synth
  - **SunriseAlarm** (`sunrise_alarm.py`, `SUNRISE_ALARM_DEVICE` set): Zigbee bedside light gradual ramp
  - **ScheduleLearner** (HA / biometric / switchbot enabled): arrival/departure/wake pattern learning + biometric sleep
  - **TimelineGenerator** (`timeline/`, always instantiated; degrades without calendar): EDF + free-window daily timeline
  - **EventAutomation** (`event_automation.py`, always instantiated; actions degrade without news/gas): event→action wiring
  - **AutomationEngine** (`automation_engine.py`): sensor_threshold / schedule / device_state / event rules
  - **SceneExecutor** (`scene_executor.py`): named multi-device scenes
  - **DeviceDispatcher** (`device_dispatcher.py`): vendor-agnostic dispatch (ha/switchbot/tapo/zigbee/mcp)
  - **TaskQueueManager / TaskReminder** (`task_scheduling/`, `task_reminder.py`): batched task queue + due reminders
  - **PersonaRewriter** (`persona_rewriter.py`, always instantiated; `PERSONA_REWRITE_ENABLED=false` disables only the rewrite behavior): rule-engine speak → character voice
  - **Annotators** (`annotator/`): EventClassifier / RulePromoter / ShoppingClassifier / ClassifierCache
  - **AckLearner** (`voice_capsule/ack_learner.py`): mobile companion ack pattern learning
  - **MotionRetriever** (`motion_retriever.py`): VRM motion via BM25 + tone affinity + usage decay + novelty, loaded from `config/motions.yaml`
- Always-on tools: `create_task`, `speak`, `get_zone_status`, `get_active_tasks`, `get_device_status`, `send_device_command` (legacy MCP), `get_sensor_history`, `add_shopping_item`, `get_shopping_list`
- Device Registry tools (default-on): `control_actuator`, `list_devices`, `describe_device`, `execute_scene_by_name`, `list_scenes`, `zigbee_permit_join`
- OpenClaw tools (profile `openclaw`; `localcraw` is a legacy alias): `get_pc_status`, `run_pc_command`, `control_browser`, `send_pc_notification`, `get_service_status`, `list_processes`
- Obsidian tools (profile `obsidian`): `search_notes`, `write_note`, `get_recent_notes`
- HA tools (profile `ha`): `control_light`, `control_climate`, `control_cover`, `get_home_devices`, `control_switch`, `get_sensor_data`, `execute_scene`, `get_entity_status`, `set_guest_mode`, `get_weather`
- Biometric tools (profile `biometric`): `get_biometrics`, `get_sleep_summary`
- Perception tools (profile `perception`): `get_perception_status`, `describe_scene`, `list_scene_objects`, `get_scene_timeline`
- News tools (profile `news`): `get_news_summary`
- Knowledge tools (profile `knowledge`): `search_knowledge`, `get_knowledge_sources`, `read_knowledge_document`
- SwitchBot tools (profile `switchbot`): `get_switchbot_devices`, `control_switchbot`, `send_switchbot_ir`
- Tapo tools (profile `tapo`): `get_power_consumption`
- GAS tools (profile `gas`): `get_recent_emails`
- Chat-only allowlist: `get_chat_tools()` filters to read-only subset (no speak / write_note / control_*)
- Tool count source-of-truth: `tool_registry.py` JSON Schemas vs `tool_dispatch.py` `TOOL_HANDLERS` (cross-reference must match)
- Schedule learner (with `ha` / `biometric` / `switchbot`): arrival/departure/wake pattern learning and prediction (+ biometric sleep data)
- Event automation (with `news` or `gas`): event→action mapping (wake_up/arrival/departure/scheduled → morning_greeting/news_briefing/weather_report/task_planning/scene)

## Chat (Personalized Conversational AI)

Interactive chat with the AI character via the dashboard. Uses agentic RAG with read-only tools.

- **Brain chat server**: Internal aiohttp.web server (:8080) alongside the MQTT cognitive loop
  - Separate ReAct loop for chat (max 3 iterations, read-only tools only)
  - Chat-specific system prompt with character personality + world context
  - Tools: search_knowledge, search_notes, get_biometrics, get_zone_status, get_weather, etc.
- **Backend chat router**: `/chat/` REST API — message persistence (Conversation/Message tables), Brain proxy, optional TTS
  - Sliding window: last 20 messages sent to Brain as conversation context
  - Auto-TTS: responses under 100 chars are synthesized via voice-service
- **Frontend ChatPanel**: Replaces AIActivityLog on dashboard
  - Unified timeline: chat messages + voice events
  - Text input + Speech-to-Text (Web Speech API, Chrome/Edge)
  - Optimistic UI with typing indicator
  - Audio playback via AudioQueue

## Event Automation

Configurable event→action mapping for automated voice briefings.

- **Events**: `wake_up` (biometric sleep end or morning camera detection), `arrival`, `departure`, `scheduled` (cron-like time)
- **Actions**: `morning_greeting` (LLM-generated), `news_briefing` (from news-bridge), `weather_report` (from world model)
- **Default**: wake_up → morning_greeting + news_briefing + weather_report
- **Configuration**: `EVENT_AUTOMATIONS` env var (JSON array)

Configure in `.env`:
```bash
NEWS_BRIDGE_URL=http://news-bridge:8000
EVENT_AUTOMATIONS='[{"event":"wake_up","actions":["morning_greeting","news_briefing","weather_report"]},{"event":"scheduled","time":"12:00","actions":["news_briefing"]}]'
```
