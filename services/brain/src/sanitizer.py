"""
Input validation and safety limits for HEMS Brain.
"""
import re
import json
import time
from typing import Dict, Any
from loguru import logger

# Allowed commands for run_pc_command (whitelist approach).
# Only permit specific safe read-only / monitoring commands.
# Each entry is (regex_pattern, description).
_ALLOWED_COMMAND_PATTERNS = [
    (r"^ls(\s+-[a-zA-Z]+)*(\s+[\w./~-]+)*$", "ls — list directory"),
    (r"^ps(\s+(aux|axu|ef|-ef|-e|-A))*$", "ps — list processes"),
    (r"^df(\s+-[a-zA-Z]+)*(\s+[\w./]+)*$", "df — disk free"),
    (r"^du(\s+-[a-zA-Z]+)*(\s+[\w./~-]+)*$", "du — disk usage"),
    (r"^uptime$", "uptime — system uptime"),
    (r"^free(\s+-[a-zA-Z]+)*$", "free — memory info"),
    (r"^top(\s+-b)?(\s+-n\s+\d+)?(\s+-p\s+[\d,]+)?$", "top — process monitor"),
    (r"^htop$", "htop — interactive process monitor"),
    (r"^uname(\s+-[a-zA-Z]+)*$", "uname — system info"),
    (r"^whoami$", "whoami — current user"),
    (r"^hostname$", "hostname — system hostname"),
    (r"^date$", "date — current date/time"),
    (r"^cat\s+/tmp/[\w./\-]+$", "cat — read /tmp file"),
    (r"^cat\s+/var/log/[\w./\-]+$", "cat — read log file"),
    (r"^tail(\s+-[a-zA-Z]+)*(\s+-n\s+\d+)?\s+/var/log/[\w./\-]+$", "tail — tail log file"),
    (r"^grep(\s+-[a-zA-Z]+)*\s+\S+\s+/var/log/[\w./\-]+$", "grep — search log file"),
    (r"^nvidia-smi(\s+--query\S+)*$", "nvidia-smi — GPU status"),
    (r"^rocm-smi$", "rocm-smi — AMD GPU status"),
    (r"^sensors$", "sensors — hardware sensors"),
    (r"^ping(\s+-c\s+\d+)?\s+[\w.\-]+$", "ping — network test"),
    (r"^systemctl\s+status\s+[\w.\-]+$", "systemctl status — service status"),
    (r"^journalctl(\s+-u\s+[\w.\-]+)?(\s+-n\s+\d+)?(\s+--no-pager)?$", "journalctl — log viewer"),
    (r"^docker\s+(ps|stats|logs)(\s+-[a-zA-Z]+)*(\s+[\w\-]+)*$", "docker — container status"),
    (r"^git\s+(status|log|diff|branch)(\s+--\S+)*(\s+[\w./\-]+)*$", "git — VCS status"),
    (r"^env(\s+\|\s+grep\s+[\w]+)?$", "env — environment variables"),
    (r"^echo\s+[\w\s.,!?-]+$", "echo — print text (safe chars only)"),
]
_ALLOWED_RES = [(re.compile(p, re.IGNORECASE), desc) for p, desc in _ALLOWED_COMMAND_PATTERNS]

# Characters/patterns that indicate injection attempts in text fields
_INJECTION_PATTERNS = [
    r"\[SYSTEM",
    r"\[INST\]",
    r"<\|system\|>",
    r"###\s*(System|Instruction|Override)",
    r"Ignore\s+previous\s+instructions",
    r"Override\s+(all\s+)?(previous\s+)?instructions",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def sanitize_llm_text(text: str) -> str:
    """Remove/escape patterns that could inject into LLM context.

    Strips prompt injection markers from sensor-derived text fields
    before they are included in the LLM context window.
    """
    if not isinstance(text, str):
        return str(text)
    # Remove injection patterns
    cleaned = _INJECTION_RE.sub("[FILTERED]", text)
    # Normalize newlines to prevent multi-line injection
    cleaned = " ".join(cleaned.splitlines())
    # Truncate very long strings
    if len(cleaned) > 500:
        cleaned = cleaned[:500] + "…"
    return cleaned


class Sanitizer:
    MAX_TASKS_PER_HOUR = 10
    SPEAK_COOLDOWN = 300  # 5 minutes per zone
    MAX_MESSAGE_LENGTH = 70

    def __init__(self):
        self.safety_limits = {
            "set_temperature": {"min": 18, "max": 28},
            "pump_duration": {"max": 60},
        }
        # Device allowlist: swarm_hub devices are always permitted (checked by prefix)
        self.allowed_devices: list[str] = ["light_01", "pump_01", "window_01"]

        # Rate limiting for task creation (timestamps recorded after successful creation)
        self._task_timestamps: list[float] = []

        # Speak cooldown per zone (recorded after successful speak)
        self._speak_cooldowns: dict[str, float] = {}

    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a tool call. Returns {"allowed": bool, "reason": str}."""
        logger.info(f"Sanitizing: {tool_name} with {arguments}")

        if tool_name == "create_task":
            return self._validate_create_task(arguments)
        elif tool_name == "send_device_command":
            return self._validate_device_command(arguments)
        elif tool_name == "speak":
            return self._validate_speak(arguments)
        elif tool_name == "run_pc_command":
            return self._validate_pc_command(arguments)
        elif tool_name == "write_note":
            return self._validate_write_note(arguments)
        elif tool_name == "control_light":
            return self._validate_control_light(arguments)
        elif tool_name == "control_climate":
            return self._validate_control_climate(arguments)
        elif tool_name == "control_cover":
            return self._validate_control_cover(arguments)
        elif tool_name == "control_switch":
            return self._validate_control_switch(arguments)
        elif tool_name == "execute_scene":
            return self._validate_execute_scene(arguments)
        elif tool_name == "control_browser":
            return self._validate_control_browser(arguments)
        elif tool_name in (
            "get_zone_status", "get_active_tasks", "get_device_status",
            "get_pc_status", "send_pc_notification",
            "get_service_status", "search_notes", "get_recent_notes",
            "get_home_devices", "get_biometrics", "get_sleep_summary",
            "get_sensor_data", "get_perception_status",
        ):
            return {"allowed": True, "reason": ""}
        else:
            logger.warning(f"REJECTED: Unknown tool {tool_name}")
            return {"allowed": False, "reason": f"Unknown tool: {tool_name}"}

    def _validate_create_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate create_task parameters."""
        now = time.time()
        # Prune old timestamps (rate limiting uses pre-recorded timestamps)
        self._task_timestamps = [t for t in self._task_timestamps if now - t < 3600]

        if len(self._task_timestamps) >= self.MAX_TASKS_PER_HOUR:
            logger.warning(f"REJECTED: Rate limit exceeded ({self.MAX_TASKS_PER_HOUR} tasks/hour)")
            return {"allowed": False, "reason": f"Rate limit: {self.MAX_TASKS_PER_HOUR} tasks/hour exceeded"}

        title = args.get("title", "")
        if not title or len(title) > 200:
            return {"allowed": False, "reason": "Invalid title"}

        xp = args.get("xp_reward", 100)
        if not isinstance(xp, (int, float)) or not (50 <= xp <= 500):
            return {"allowed": False, "reason": f"xp_reward {xp} out of range (50-500)"}

        urgency = args.get("urgency", 2)
        if isinstance(urgency, (int, float)) and not (0 <= urgency <= 4):
            logger.warning(f"REJECTED: Urgency {urgency} out of range 0-4")
            return {"allowed": False, "reason": f"urgency {urgency} out of range (0-4)"}

        return {"allowed": True, "reason": ""}

    def record_task_created(self):
        """Record a successful task creation for rate limiting."""
        self._task_timestamps.append(time.time())

    def _validate_speak(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate speak parameters with zone-based cooldown."""
        message = args.get("message", "")
        if not message or not message.strip():
            return {"allowed": False, "reason": "Empty message"}

        if len(message) > self.MAX_MESSAGE_LENGTH:
            logger.warning(f"Speak message too long ({len(message)} > {self.MAX_MESSAGE_LENGTH}), truncating")
            args["message"] = message[:self.MAX_MESSAGE_LENGTH]

        zone = args.get("zone", "unknown")
        now = time.time()
        last_speak = self._speak_cooldowns.get(zone, 0)
        if now - last_speak < self.SPEAK_COOLDOWN:
            remaining = int(self.SPEAK_COOLDOWN - (now - last_speak))
            logger.warning(f"REJECTED: speak cooldown for zone {zone} ({remaining}s remaining)")
            return {"allowed": False, "reason": f"Speak cooldown for zone '{zone}': {remaining}s remaining"}

        return {"allowed": True, "reason": ""}

    def record_speak(self, zone: str = "general"):
        """Record a successful speak execution for cooldown tracking."""
        self._speak_cooldowns[zone] = time.time()

    def _validate_device_command(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate send_device_command parameters."""
        agent_id = args.get("agent_id", "")
        tool_name = args.get("tool_name", "")

        # Device allowlist check: swarm_hub devices always permitted
        if not agent_id.startswith("swarm_hub") and agent_id not in self.allowed_devices:
            logger.warning(f"REJECTED: Device {agent_id} not in allowed list")
            return {"allowed": False, "reason": f"Device '{agent_id}' is not in the allowed device list"}

        # Parse nested arguments if string
        inner_args = args.get("arguments", {})
        if isinstance(inner_args, str):
            try:
                inner_args = json.loads(inner_args)
            except (json.JSONDecodeError, TypeError):
                inner_args = {}

        # Temperature range check
        if tool_name == "set_temperature":
            temp = inner_args.get("temperature")
            if temp is not None:
                limits = self.safety_limits["set_temperature"]
                if not (limits["min"] <= temp <= limits["max"]):
                    logger.warning(f"REJECTED: Temperature {temp} out of bounds [{limits['min']}-{limits['max']}]")
                    return {"allowed": False, "reason": f"Temperature {temp} out of safe range [{limits['min']}-{limits['max']}]"}

        # Pump duration check
        if tool_name == "run_pump":
            duration = inner_args.get("duration")
            if duration is not None:
                if duration > self.safety_limits["pump_duration"]["max"]:
                    logger.warning(f"REJECTED: Pump duration {duration} exceeds limit")
                    return {"allowed": False, "reason": f"Pump duration {duration}s exceeds maximum {self.safety_limits['pump_duration']['max']}s"}

        return {"allowed": True, "reason": ""}

    def _validate_write_note(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate write_note parameters (Obsidian integration)."""
        title = args.get("title", "")
        if not title:
            return {"allowed": False, "reason": "Empty title"}

        # Path traversal prevention — check for traversal sequences
        if ".." in title or title.startswith("/"):
            return {"allowed": False, "reason": "Path traversal detected in title"}

        category = args.get("category", "")
        if category and (".." in category or "/" in category):
            return {"allowed": False, "reason": "Path traversal detected in category"}

        content = args.get("content", "")
        if len(content) > 10000:
            return {"allowed": False, "reason": f"Content too long ({len(content)} > 10000)"}

        return {"allowed": True, "reason": ""}

    def _validate_pc_command(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate run_pc_command against an explicit allowlist.

        Only commands that match a known-safe pattern are permitted.
        This whitelist approach is safer than a blocklist because it prevents
        novel bypass techniques (shell wrappers, subshells, interpreters, etc.).
        """
        command = args.get("command", "").strip()
        if not command:
            return {"allowed": False, "reason": "Empty command"}

        for pattern, desc in _ALLOWED_RES:
            if pattern.match(command):
                logger.debug(f"PC command allowed ({desc}): {command[:60]}")
                return {"allowed": True, "reason": ""}

        logger.warning(f"PC command not in allowlist: {command[:100]}")
        return {
            "allowed": False,
            "reason": (
                f"Command not in allowlist. Permitted: read-only monitoring commands "
                f"(ls, ps, df, uptime, sensors, nvidia-smi, systemctl status, etc.)"
            ),
        }

    def _validate_control_light(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate control_light parameters."""
        entity_id = args.get("entity_id", "")
        if not entity_id:
            return {"allowed": False, "reason": "Missing entity_id"}

        brightness = args.get("brightness")
        if brightness is not None and not (0 <= brightness <= 255):
            return {"allowed": False, "reason": f"Brightness {brightness} out of range (0-255)"}

        color_temp = args.get("color_temp")
        if color_temp is not None and not (153 <= color_temp <= 500):
            return {"allowed": False, "reason": f"Color temp {color_temp} out of range (153-500)"}

        return {"allowed": True, "reason": ""}

    def _validate_control_climate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate control_climate parameters."""
        entity_id = args.get("entity_id", "")
        if not entity_id:
            return {"allowed": False, "reason": "Missing entity_id"}

        _VALID_MODES = {"off", "cool", "heat", "dry", "fan_only", "auto"}
        mode = args.get("mode")
        if mode and mode not in _VALID_MODES:
            return {"allowed": False, "reason": f"Invalid mode '{mode}'. Allowed: {_VALID_MODES}"}

        temperature = args.get("temperature")
        if temperature is not None and not (16 <= temperature <= 30):
            return {"allowed": False, "reason": f"Temperature {temperature} out of range (16-30)"}

        return {"allowed": True, "reason": ""}

    def _validate_control_cover(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate control_cover parameters."""
        entity_id = args.get("entity_id", "")
        if not entity_id:
            return {"allowed": False, "reason": "Missing entity_id"}

        position = args.get("position")
        if position is not None and not (0 <= position <= 100):
            return {"allowed": False, "reason": f"Position {position} out of range (0-100)"}

        return {"allowed": True, "reason": ""}

    def _validate_control_switch(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate control_switch parameters."""
        entity_id = args.get("entity_id", "")
        if not entity_id:
            return {"allowed": False, "reason": "Missing entity_id"}
        if not entity_id.startswith("switch."):
            return {"allowed": False, "reason": f"Invalid entity_id prefix: expected 'switch.' but got '{entity_id}'"}
        return {"allowed": True, "reason": ""}

    def _validate_execute_scene(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate execute_scene parameters."""
        entity_id = args.get("entity_id", "")
        if not entity_id:
            return {"allowed": False, "reason": "Missing entity_id"}
        if not entity_id.startswith("scene."):
            return {"allowed": False, "reason": f"Invalid entity_id prefix: expected 'scene.' but got '{entity_id}'"}
        return {"allowed": True, "reason": ""}

    def _validate_control_browser(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate control_browser parameters.

        The 'eval' action executes arbitrary JavaScript and is blocked
        to prevent LLM-generated code from running unvetted in the browser.
        """
        action = args.get("action", "")
        _ALLOWED_ACTIONS = {"navigate", "get_url", "get_title"}

        if action not in _ALLOWED_ACTIONS:
            logger.warning(f"REJECTED: control_browser action '{action}' not allowed")
            return {
                "allowed": False,
                "reason": (
                    f"Browser action '{action}' is not permitted. "
                    f"Allowed: {_ALLOWED_ACTIONS}. "
                    f"The 'eval' action is disabled to prevent arbitrary JS execution."
                ),
            }

        # Validate URL for navigate
        if action == "navigate":
            url = args.get("url", "")
            if not url.startswith(("http://", "https://")):
                return {"allowed": False, "reason": f"Invalid URL scheme for navigate: {url[:80]}"}

        return {"allowed": True, "reason": ""}
