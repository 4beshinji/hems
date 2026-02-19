"""
Input validation and safety limits for HEMS Brain.
"""
import json
import re
import time
from typing import Dict, Any
from loguru import logger

# Dangerous command patterns for run_pc_command
_DANGEROUS_PATTERNS = [
    r"\brm\s+-\S*[rf]\S*\s",  # rm with -r or -f flags (rm -rf, rm -f, rm -r)
    r"\bmkfs\b",
    r"\bdd\s+.*of=/dev/",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\binit\s+0\b",
    r"\bsystemctl\s+(halt|poweroff|reboot)\b",
    r">\s*/dev/sd[a-z]",
    r"\bchmod\s+(-\S+\s+)*777\s+/",
    r"\bchown\s+\S+\s+/",
    r":\(\)\s*\{.*:\|:.*\};",  # fork bomb
]
_DANGEROUS_RE = [re.compile(p) for p in _DANGEROUS_PATTERNS]


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
        elif tool_name in (
            "get_zone_status", "get_active_tasks", "get_device_status",
            "get_pc_status", "control_browser", "send_pc_notification",
            "get_service_status", "search_notes", "get_recent_notes",
            "get_home_devices", "get_biometrics", "get_sleep_summary",
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

        # Path traversal prevention
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
        """Validate run_pc_command against dangerous pattern blocklist."""
        command = args.get("command", "")
        if not command:
            return {"allowed": False, "reason": "Empty command"}

        for pattern in _DANGEROUS_RE:
            if pattern.search(command):
                logger.warning(f"Dangerous PC command blocked: {command[:100]}")
                return {"allowed": False, "reason": "Dangerous command pattern detected"}

        return {"allowed": True, "reason": ""}

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
