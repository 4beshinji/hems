"""
Input validation and safety limits for HEMS Brain.
"""
import re
import time
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
        self._task_timestamps: list[float] = []
        self._speak_cooldowns: dict[str, float] = {}

    def validate_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """Validate a tool call. Returns {"allowed": bool, "reason": str}."""
        if tool_name == "create_task":
            return self._validate_create_task(arguments)
        elif tool_name == "speak":
            return self._validate_speak(arguments)
        elif tool_name == "run_pc_command":
            return self._validate_pc_command(arguments)
        elif tool_name == "write_note":
            return self._validate_write_note(arguments)
        elif tool_name in ("send_device_command", "get_zone_status",
                           "get_pc_status", "control_browser", "send_pc_notification",
                           "get_service_status", "search_notes", "get_recent_notes"):
            return {"allowed": True, "reason": ""}
        else:
            return {"allowed": False, "reason": f"Unknown tool: {tool_name}"}

    def _validate_create_task(self, args: dict) -> dict:
        now = time.time()
        # Prune old timestamps
        self._task_timestamps = [t for t in self._task_timestamps if now - t < 3600]

        if len(self._task_timestamps) >= self.MAX_TASKS_PER_HOUR:
            return {"allowed": False, "reason": f"Rate limit: {self.MAX_TASKS_PER_HOUR} tasks/hour exceeded"}

        title = args.get("title", "")
        if not title or len(title) > 200:
            return {"allowed": False, "reason": "Invalid title"}

        xp = args.get("xp_reward", 100)
        if not (50 <= xp <= 500):
            return {"allowed": False, "reason": f"xp_reward {xp} out of range (50-500)"}

        urgency = args.get("urgency", 2)
        if not (0 <= urgency <= 4):
            return {"allowed": False, "reason": f"urgency {urgency} out of range (0-4)"}

        self._task_timestamps.append(now)
        return {"allowed": True, "reason": ""}

    def _validate_speak(self, args: dict) -> dict:
        message = args.get("message", "")
        if not message:
            return {"allowed": False, "reason": "Empty message"}

        if len(message) > self.MAX_MESSAGE_LENGTH:
            logger.warning(f"Speak message too long ({len(message)} > {self.MAX_MESSAGE_LENGTH}), truncating")
            args["message"] = message[:self.MAX_MESSAGE_LENGTH]

        zone = args.get("zone", "unknown")
        now = time.time()
        last_speak = self._speak_cooldowns.get(zone, 0)
        if now - last_speak < self.SPEAK_COOLDOWN:
            remaining = int(self.SPEAK_COOLDOWN - (now - last_speak))
            return {"allowed": False, "reason": f"Speak cooldown for zone '{zone}': {remaining}s remaining"}

        self._speak_cooldowns[zone] = now
        return {"allowed": True, "reason": ""}

    def _validate_write_note(self, args: dict) -> dict:
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

    def _validate_pc_command(self, args: dict) -> dict:
        command = args.get("command", "")
        if not command:
            return {"allowed": False, "reason": "Empty command"}

        for pattern in _DANGEROUS_RE:
            if pattern.search(command):
                logger.warning(f"Dangerous PC command blocked: {command[:100]}")
                return {"allowed": False, "reason": f"Dangerous command pattern detected"}

        return {"allowed": True, "reason": ""}
