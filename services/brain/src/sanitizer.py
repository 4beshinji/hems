"""
Input validation and safety limits for HEMS Brain.
"""
import time
from loguru import logger


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
        elif tool_name in ("send_device_command", "get_zone_status"):
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
