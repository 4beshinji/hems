"""
Rule-based fallback engine for HEMS Brain.
Used when GPU load is high or LLM is unavailable.
Evaluates simple threshold rules and returns tool call actions.
"""
import os
import subprocess
import time
from loguru import logger


GPU_TYPE = os.getenv("GPU_TYPE", "none")  # amd | nvidia | none
GPU_HIGH_LOAD_THRESHOLD = int(os.getenv("GPU_HIGH_LOAD_THRESHOLD", "80"))


def _get_gpu_utilization() -> float | None:
    """Query GPU utilization percentage. Returns None if unavailable."""
    try:
        if GPU_TYPE == "nvidia":
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                timeout=5, text=True,
            )
            return float(out.strip().split("\n")[0])
        elif GPU_TYPE == "amd":
            out = subprocess.check_output(
                ["rocm-smi", "--showuse", "--csv"],
                timeout=5, text=True,
            )
            for line in out.strip().split("\n"):
                if "," in line and not line.startswith("device"):
                    parts = line.split(",")
                    if len(parts) >= 2:
                        try:
                            return float(parts[1].strip().replace("%", ""))
                        except ValueError:
                            pass
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError) as e:
        logger.debug(f"GPU query failed: {e}")
    return None


class RuleEngine:
    """Threshold-based decision engine — no LLM required."""

    # Cooldowns to prevent repeated actions (zone -> last_action_time)
    _cooldowns: dict[str, float] = {}
    COOLDOWN_SECONDS = 300  # 5 minutes

    def should_use_rules(self) -> bool:
        """Check if we should use rule-based mode instead of LLM."""
        if GPU_TYPE == "none":
            return False
        util = _get_gpu_utilization()
        if util is not None and util > GPU_HIGH_LOAD_THRESHOLD:
            return True
        return False

    def evaluate(self, world_model) -> list[dict]:
        """Evaluate rules against current world state. Returns list of tool call actions."""
        actions = []
        now = time.time()

        for zone_id, zone in world_model.zones.items():
            env = zone.environment

            # CO2 > 1000ppm -> create ventilation task
            if env.co2 is not None and env.co2 > 1000:
                if self._check_cooldown(f"co2_{zone_id}", now):
                    actions.append({
                        "tool": "create_task",
                        "args": {
                            "title": f"{zone_id}の換気",
                            "description": f"CO2濃度が{int(env.co2)}ppmです。窓を開けて換気してください。",
                            "xp_reward": 100,
                            "urgency": 3,
                            "zone": zone_id,
                            "task_type": ["ventilation"],
                        },
                    })

            # Temperature too high (>28) or too low (<16)
            if env.temperature is not None:
                if env.temperature > 28 and self._check_cooldown(f"temp_high_{zone_id}", now):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"{zone_id}の室温が{env.temperature:.1f}度です。エアコンをつけましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    })
                elif env.temperature < 16 and self._check_cooldown(f"temp_low_{zone_id}", now):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"{zone_id}の室温が{env.temperature:.1f}度と低めです。暖房をつけましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    })

            # Sedentary detection (from events)
            for event in zone.events:
                if event.event_type == "sedentary_alert" and self._check_cooldown(f"sed_{zone_id}", now):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": "長時間座っていますね。少し休憩しましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    })

        return actions

    def _check_cooldown(self, key: str, now: float) -> bool:
        """Check and set cooldown. Returns True if action is allowed."""
        last = self._cooldowns.get(key, 0)
        if now - last < self.COOLDOWN_SECONDS:
            return False
        self._cooldowns[key] = now
        return True
