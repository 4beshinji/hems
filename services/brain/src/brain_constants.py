import os

from dotenv import load_dotenv

load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
LLM_API_URL = os.getenv("LLM_API_URL", "http://mock-llm:8000/v1")
OPENCLAW_BRIDGE_URL = os.getenv("OPENCLAW_BRIDGE_URL", os.getenv("LOCALCRAW_BRIDGE_URL", ""))
# Backward-compatible alias for older .env files.
LOCALCRAW_BRIDGE_URL = OPENCLAW_BRIDGE_URL
OPENCLAW_ENABLED = bool(OPENCLAW_BRIDGE_URL)
OBSIDIAN_BRIDGE_URL = os.getenv("OBSIDIAN_BRIDGE_URL", "")
OBSIDIAN_ENABLED = bool(OBSIDIAN_BRIDGE_URL)
GAS_BRIDGE_URL = os.getenv("GAS_BRIDGE_URL", "")
GAS_ENABLED = bool(GAS_BRIDGE_URL)
HA_BRIDGE_URL = os.getenv("HA_BRIDGE_URL", "")
HA_ENABLED = bool(HA_BRIDGE_URL)
BIOMETRIC_BRIDGE_URL = os.getenv("BIOMETRIC_BRIDGE_URL", "")
BIOMETRIC_ENABLED = bool(BIOMETRIC_BRIDGE_URL)
PERCEPTION_BRIDGE_URL = os.getenv("PERCEPTION_BRIDGE_URL", "")
PERCEPTION_ENABLED = bool(PERCEPTION_BRIDGE_URL)
SWITCHBOT_BRIDGE_URL = os.getenv("SWITCHBOT_BRIDGE_URL", "")
SWITCHBOT_ENABLED = bool(SWITCHBOT_BRIDGE_URL)
NEWS_BRIDGE_URL = os.getenv("NEWS_BRIDGE_URL", "")
NEWS_ENABLED = bool(NEWS_BRIDGE_URL)
KNOWLEDGE_BRIDGE_URL = os.getenv("KNOWLEDGE_BRIDGE_URL", "")
KNOWLEDGE_ENABLED = bool(KNOWLEDGE_BRIDGE_URL)
TAPO_BRIDGE_URL = os.getenv("TAPO_BRIDGE_URL", "")
TAPO_ENABLED = bool(TAPO_BRIDGE_URL)

VOICE_SERVICE_URL = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")
BACKEND_URL = os.getenv("DASHBOARD_API_URL", os.getenv("BACKEND_URL", "http://backend:8000"))


def backend_auth_headers() -> dict:
    """Auth header for brain → backend dashboard-router calls.

    Matches the backend ``verify_api_key`` gate (``auth.verify_api_key``):
    every router protected by ``BACKEND_API_KEY`` expects
    ``Authorization: Bearer <BACKEND_API_KEY>``. Returns ``{}`` when the key
    is unset (backend then runs open / LAN-trusted), so zero-config
    deployments are unaffected. Read each call to pick up hot-reloaded env.

    Note: this is a *different* secret from ``HEMS_INTERNAL_TOKEN`` (the
    voice-service / stt gate). Backend-bound requests use this; voice/stt
    requests keep ``HEMS_INTERNAL_TOKEN``.
    """
    key = os.getenv("BACKEND_API_KEY", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


BOOT_LOAD_ENABLED = os.getenv("BOOT_LOAD_ENABLED", "true").lower() in ("true", "1", "yes")

# Camera-based wake_up detection time window (24h clock). Defaults 5–11 inclusive of 10am.
WAKE_DETECT_HOUR_START = int(os.getenv("WAKE_DETECT_HOUR_START", "5"))
WAKE_DETECT_HOUR_END = int(os.getenv("WAKE_DETECT_HOUR_END", "11"))

CHAT_SERVER_PORT = int(os.getenv("BRAIN_CHAT_PORT", "8080"))
CHAT_MAX_ITERATIONS = 3

SCHEDULE_STATE_PATH = os.getenv("SCHEDULE_STATE_PATH", "/app/data/schedule_learner_state.json")

REACT_MAX_ITERATIONS = 5
CYCLE_INTERVAL = 30
EVENT_BATCH_DELAY = 3
MIN_CYCLE_INTERVAL = 25
MAX_SPEAK_PER_CYCLE = 1
MAX_CONSECUTIVE_ERRORS = 1
EFFICACY_EVAL_INTERVAL = 300  # 5 min — how often to score completed interventions

# Cognitive cycle time windows (seconds)
RECENT_EVENT_WINDOW_SEC = 300  # events newer than this are surfaced in LLM context
RECENT_ACTION_WINDOW_SEC = 1800  # action-history lookback for dedup + context injection
GPU_FRESHNESS_SEC = 600  # GPU telemetry considered stale beyond this
ACTION_HISTORY_RETENTION_SEC = 7200  # prune action history older than this
SECONDS_PER_DAY = 86400  # 24h windows (bridge outage dedup, efficacy verdict retention)

# Degraded operation (Group C): tools suppressed in observe-only ("blind") mode,
# i.e. when every zone's sensors have gone stale. Anything that creates a task
# or actuates the physical environment is dropped so the brain never acts on a
# stale world view; read/query tools and speak stay allowed so it keeps
# situational awareness and can still talk to the user. PC/digital actions
# (control_browser, run_pc_command) are not gated — they don't depend on
# physical sensor freshness.
BLIND_SUPPRESSED_TOOLS = frozenset(
    {
        "create_task",
        "send_device_command",
        "control_actuator",
        "control_light",
        "control_climate",
        "control_cover",
        "control_switch",
        "control_switchbot",
        "send_switchbot_ir",
        "execute_scene",
        "execute_scene_by_name",
        "zigbee_permit_join",
    }
)


# tool_name → summarizer. Dispatch table keeps the per-tool one-liners flat and
# makes a missing tool obvious; unknown tools fall back to a truncated repr.
_ACTION_SUMMARIZERS = {
    # Always-on
    "speak": lambda a: f"zone={a.get('zone', '?')}, msg={a.get('message', '')[:30]}",
    "create_task": lambda a: f"title={a.get('title', '')}",
    "get_zone_status": lambda a: f"zone={a.get('zone_id', '')}",
    "get_active_tasks": lambda a: "active_tasks",
    "get_device_status": lambda a: f"device={a.get('device_id', 'all')}",
    "send_device_command": lambda a: f"agent={a.get('agent_id', '')}, tool={a.get('tool_name', '')}",
    "get_sensor_history": lambda a: f"zone={a.get('zone_id', '')}, channel={a.get('channel', '')}",
    "add_shopping_item": lambda a: f"item={a.get('name', '')[:30]}",
    "get_shopping_list": lambda a: "shopping_list",
    # Device Registry
    "control_actuator": lambda a: f"device={a.get('device_id', '')}, action={a.get('action', '')}",
    "list_devices": lambda a: f"vendor={a.get('vendor', 'all')}",
    "describe_device": lambda a: f"device={a.get('device_id', '')}",
    "execute_scene_by_name": lambda a: f"scene={a.get('name', '')}",
    "list_scenes": lambda a: "scenes",
    "zigbee_permit_join": lambda a: f"enable={a.get('enable', '')}",
    # OpenClaw
    "run_pc_command": lambda a: f"cmd={a.get('command', '')[:40]}",
    "control_browser": lambda a: f"action={a.get('action', '')}",
    "send_pc_notification": lambda a: f"title={a.get('title', '')[:30]}",
    "get_pc_status": lambda a: "pc_status",
    "get_service_status": lambda a: f"service={a.get('service_name', 'all')}",
    "list_processes": lambda a: "processes",
    # Obsidian
    "search_notes": lambda a: f"query={a.get('query', '')[:30]}",
    "write_note": lambda a: f"title={a.get('title', '')[:30]}",
    "get_recent_notes": lambda a: f"limit={a.get('limit', 5)}",
    # HA
    "control_light": lambda a: f"entity={a.get('entity_id', '')}, on={a.get('on', '')}",
    "control_climate": lambda a: f"entity={a.get('entity_id', '')}, mode={a.get('mode', '')}",
    "control_cover": lambda a: f"entity={a.get('entity_id', '')}, action={a.get('action', '')}",
    "get_home_devices": lambda a: "home_devices",
    "control_switch": lambda a: f"entity={a.get('entity_id', '')}, on={a.get('on', '')}",
    "get_sensor_data": lambda a: f"entity={a.get('entity_id', 'all')}, class={a.get('device_class', 'all')}",
    "execute_scene": lambda a: f"entity={a.get('entity_id', '')}",
    "get_entity_status": lambda a: f"entity={a.get('entity_id', '')}",
    "set_guest_mode": lambda a: f"enabled={a.get('enabled', '')}, hours={a.get('duration_hours', '')}",
    "get_weather": lambda a: "weather",
    # Biometric
    "get_biometrics": lambda a: "biometrics",
    "get_sleep_summary": lambda a: "sleep_summary",
    # Perception
    "get_perception_status": lambda a: "perception_status",
    "describe_scene": lambda a: f"zone={a.get('zone_id', 'all')}",
    "list_scene_objects": lambda a: f"zone={a.get('zone_id', 'all')}",
    "get_scene_timeline": lambda a: f"zone={a.get('zone_id', 'all')}",
    # SwitchBot
    "get_switchbot_devices": lambda a: "switchbot_devices",
    "control_switchbot": lambda a: f"device={a.get('device_id', '')}, cmd={a.get('command', '')}",
    "send_switchbot_ir": lambda a: f"ir_device={a.get('device_id', '')}, cmd={a.get('command', '')}",
    # Tapo
    "get_power_consumption": lambda a: f"device={a.get('device_id', '')}",
    # News
    "get_news_summary": lambda a: "news_summary",
    # Knowledge
    "search_knowledge": lambda a: f"query={a.get('query', '')[:30]}",
    "get_knowledge_sources": lambda a: "knowledge_sources",
    "read_knowledge_document": lambda a: f"doc={a.get('doc_id', '')}",
    # GAS
    "get_recent_emails": lambda a: f"max={a.get('max_results', '')}",
}


def summarize_action(tool_name: str, args: dict) -> str:
    fn = _ACTION_SUMMARIZERS.get(tool_name)
    return fn(args) if fn else str(args)[:50]
