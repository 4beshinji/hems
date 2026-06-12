"""
Rule-based fallback engine for HEMS Brain.
Used when GPU load is high or LLM is unavailable.
Evaluates simple threshold rules and returns tool call actions.
"""

import random  # noqa: F401 - used by extracted rule mixins
import subprocess
import time
from datetime import UTC, datetime  # noqa: F401 - used by extracted rule mixins

from loguru import logger

from brain_utils import parse_iso_ts  # noqa: F401 - used by extracted rule mixins
from rules.config import RuleThresholds, load_rule_thresholds
from schedule_learner import ScheduleLearner


def _get_gpu_utilization(gpu_type: str) -> float | None:
    """Query GPU utilization percentage. Returns None if unavailable."""
    try:
        if gpu_type == "nvidia":
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                timeout=5,
                text=True,
            )
            return float(out.strip().split("\n")[0])
        elif gpu_type == "amd":
            out = subprocess.check_output(
                ["rocm-smi", "--showuse", "--csv"],
                timeout=5,
                text=True,
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


from rules.biometric import BiometricRulesMixin
from rules.environment import EnvironmentRulesMixin
from rules.gas import GasRulesMixin
from rules.home import HomeRulesMixin
from rules.pc import PCRulesMixin
from rules.perception import PerceptionRulesMixin
from rules.services import ServiceRulesMixin
from rules.shopping import ShoppingRulesMixin
from rules.weather import WeatherRulesMixin
from rules.zigbee import ZigbeeRulesMixin


class RuleEngine(
    ShoppingRulesMixin,
    WeatherRulesMixin,
    GasRulesMixin,
    PerceptionRulesMixin,
    ServiceRulesMixin,
    BiometricRulesMixin,
    HomeRulesMixin,
    ZigbeeRulesMixin,
    EnvironmentRulesMixin,
    PCRulesMixin,
):
    """Threshold-based decision engine — no LLM required."""

    COOLDOWN_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        schedule_learner: ScheduleLearner | None = None,
        mqtt_publisher=None,
        thresholds: RuleThresholds | None = None,
    ):
        # Single source of truth for thresholds (constructor DI, W2.3).
        # Falls back to env-loaded defaults when not injected. Brain shares the
        # same RuleThresholds instance held by WorldModel (see main.py).
        self.thresholds: RuleThresholds = thresholds or load_rule_thresholds()
        self.schedule_learner = schedule_learner
        self.device_dispatcher = None
        self.mqtt_publisher = mqtt_publisher  # Callable[[str, dict], None] — fire-and-forget publish
        self._cooldowns: dict[str, float] = {}
        self._pressure_history: dict[str, float] = {}  # zone_id → last known pressure
        self._absence_light_state: dict[str, bool] = {}  # device_id → simulated on
        self._device_cache: list[dict] = []
        self._device_cache_ts: float = 0
        self._DEVICE_CACHE_TTL = 60
        # Sustained-condition trackers: zone_id → first observation timestamp
        self._voc_high_since: dict[str, float] = {}
        self._low_pressure_since: dict[str, float] = {}
        self._low_light_since: dict[str, float] = {}
        self._high_light_since: dict[str, float] = {}
        # Heavy process tracker: process_name → first observation timestamp (CPU > 90%)
        self._heavy_proc_since: dict[str, float] = {}

    async def refresh_devices(self):
        if self.device_dispatcher is None:
            return
        now = time.time()
        if now - self._device_cache_ts < self._DEVICE_CACHE_TTL:
            return
        self._device_cache = await self.device_dispatcher.list_all()
        self._device_cache_ts = now

    def _get_devices(self, device_class=None, capability=None, zone=None, kind=None) -> list[dict]:
        results = []
        for d in self._device_cache:
            if not d.get("is_enabled", True):
                continue
            if device_class and d.get("device_class") != device_class:
                continue
            if capability and capability not in (d.get("capabilities") or []):
                continue
            if zone and d.get("zone") != zone:
                continue
            if kind and d.get("kind") != kind:
                continue
            results.append(d)
        return results

    def _device_is_on(self, device: dict) -> bool:
        return (device.get("last_state") or {}).get("on", False)

    def _device_brightness(self, device: dict) -> int:
        return (device.get("last_state") or {}).get("brightness", 0)

    @staticmethod
    def _make_action(device_id: str, action: str, params: dict | None = None) -> dict:
        return {
            "tool": "control_actuator",
            "args": {"device_id": device_id, "action": action, "params": params or {}},
        }

    def should_use_rules(self) -> bool:
        """Check if we should use rule-based mode instead of LLM."""
        if self.thresholds.gpu_type == "none":
            return False
        util = _get_gpu_utilization(self.thresholds.gpu_type)
        if util is not None and util > self.thresholds.gpu_high_load_threshold:
            return True
        return False

    def evaluate(self, world_model) -> list[dict]:
        """Evaluate rules against current world state. Returns list of tool call actions.

        Thin orchestrator (W2.4): each domain block was extracted into a mixin
        method.  The call order below is the *exact* source order of the former
        inline blocks, so the emitted action list is unchanged.  In particular
        the loop-external PC blocks are interleaved with the mixin calls just as
        they were inline (P1/P2 → device_health → service_vip → VLM → P3 →
        GAS → home/zigbee → screen_time → biometric → perception → shopping).
        """
        actions = []
        now = time.time()

        # --- Per-zone environment rules (Z1..Z12) ---
        for zone_id, zone in world_model.zones.items():
            actions.extend(self._evaluate_zone_environment(zone_id, zone, now))

        # --- PC rules: GPU temp + disk (P1, P2) ---
        actions.extend(self._evaluate_pc_basic_rules(world_model, now))

        # --- Device battery / link quality / last_seen rules (B-5) ---
        actions.extend(self._evaluate_device_health_rules(now))

        # --- Service VIP event rules (B-2) ---
        actions.extend(self._evaluate_service_vip_rules(world_model, now))

        # --- VLM swap stuck rule (B-3) ---
        actions.extend(self._evaluate_vlm_swap(world_model, now))

        # --- Heavy process rules (B-1) ---
        actions.extend(self._evaluate_heavy_processes(world_model, now))

        # --- GAS rules ---
        gas = world_model.gas_state
        if gas.bridge_connected:
            actions.extend(self._evaluate_gas_rules(gas, now, world_model))

        # --- Home / device rules ---
        hd = world_model.home_devices
        has_devices = hd.bridge_connected or bool(self._device_cache)
        if has_devices:
            if not world_model.is_guest_mode:
                actions.extend(self._evaluate_home_rules(world_model, now))
                actions.extend(self._evaluate_zigbee_sensor_rules(world_model, now))
                actions.extend(self._evaluate_circadian_lighting(world_model, now))
                actions.extend(self._evaluate_absence_lighting(world_model, now))
                actions.extend(self._evaluate_weather_rules(world_model, now))
            else:
                # Guest mode: only critical safety rules from zigbee sensors
                actions.extend(self._evaluate_zigbee_critical_only(world_model, now))

        # --- Screen time rule (Z13) ---
        actions.extend(self._evaluate_screen_time(world_model, now))

        # --- Biometric rules (skip in guest mode for privacy) ---
        bio = world_model.biometric_state
        if bio.bridge_connected and not world_model.is_guest_mode:
            actions.extend(self._evaluate_biometric_rules(world_model, now))

        # --- Perception rules ---
        actions.extend(self._evaluate_perception_rules(world_model, now))

        # --- Shopping list rules ---
        actions.extend(self._evaluate_shopping_rules(world_model, now))

        return actions

    def _check_cooldown(self, key: str, now: float) -> bool:
        """Check and set cooldown. Returns True if action is allowed."""
        last = self._cooldowns.get(key, 0)
        if now - last < self.COOLDOWN_SECONDS:
            return False
        self._cooldowns[key] = now
        return True

    def _check_cooldown_daily(self, key: str, now: float) -> bool:
        """Check and set daily cooldown (24h). Returns True if action is allowed."""
        last = self._cooldowns.get(key, 0)
        if now - last < 86400:  # 24 hours
            return False
        self._cooldowns[key] = now
        return True

    def _check_cooldown_custom(self, key: str, now: float, duration_s: int) -> bool:
        """Check and set cooldown with an explicit duration. Returns True if allowed."""
        last = self._cooldowns.get(key, 0)
        if now - last < duration_s:
            return False
        self._cooldowns[key] = now
        return True

    def evaluate_critical(self, world_model) -> list[dict]:
        """Evaluate life-safety critical rules only.

        Used in low-power mode (sleep / away) to respond to dangerous conditions
        without running the full rule set or the LLM.  Only fires on conditions
        that genuinely require immediate action regardless of occupancy or time.
        """
        actions = []
        now = time.time()

        # --- Environmental: CO2 danger level ---
        for zone_id, zone in world_model.zones.items():
            env = zone.environment
            if (
                env.co2 is not None
                and env.co2 > self.thresholds.co2_critical
                and self._check_cooldown(f"critical_co2_{zone_id}", now)
            ):
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": f"【緊急】{zone_id}のCO2危険レベル",
                            "description": (f"CO2濃度が{int(env.co2)}ppmです。直ちに換気してください。"),
                            "urgency": 4,
                            "zone": zone_id,
                            "task_type": ["ventilation"],
                        },
                    }
                )
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": (
                                f"緊急です！{zone_id}のCO2濃度が{int(env.co2)}ppmです。すぐに換気してください！"
                            ),
                            "zone": zone_id,
                            "tone": "alert",
                        },
                    }
                )

            # --- Environmental: extreme temperature ---
            if env.temperature is not None:
                if env.temperature > self.thresholds.temp_critical_high and self._check_cooldown(
                    f"critical_temp_high_{zone_id}", now
                ):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": (
                                    f"危険！{zone_id}の室温が{env.temperature:.1f}℃です。熱中症に注意してください！"
                                ),
                                "zone": zone_id,
                                "tone": "alert",
                            },
                        }
                    )
                elif env.temperature < self.thresholds.temp_critical_low and self._check_cooldown(
                    f"critical_temp_low_{zone_id}", now
                ):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": (
                                    f"危険！{zone_id}の室温が{env.temperature:.1f}℃まで低下しています。"
                                    "暖房を確認してください！"
                                ),
                                "zone": zone_id,
                                "tone": "alert",
                            },
                        }
                    )

        # --- Zigbee: Moisture emergency (water leak) ---
        hd = world_model.home_devices
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "moisture" and bs.state:
                if self._check_cooldown(f"critical_moisture_{eid}", now):
                    name = eid.split(".")[-1] if "." in eid else eid
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"【緊急】水漏れ検知: {name}",
                                "description": f"{name}で水漏れが検知されました。直ちに確認してください。",
                                "urgency": 4,
                                "zone": "home",
                                "task_type": ["water_leak"],
                            },
                        }
                    )
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"緊急！{name}で水漏れを検知しました！すぐに確認してください！",
                                "zone": "home",
                                "tone": "alert",
                            },
                        }
                    )

        # --- Biometric: SpO2 critical drop (sleep apnea risk) ---
        bio = world_model.biometric_state
        if (
            bio.spo2.percent is not None
            and bio.spo2.percent < self.thresholds.spo2_critical_low
            and bio.spo2.last_update > now - 300
            and self._check_cooldown("critical_spo2", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": (
                            f"緊急！血中酸素濃度が{bio.spo2.percent}%まで低下しています！目を覚ましてください！"
                        ),
                        "zone": "home",
                        "tone": "alert",
                    },
                }
            )

        # --- Biometric: very high heart rate during sleep ---
        if (
            bio.heart_rate.bpm is not None
            and bio.heart_rate.bpm > self.thresholds.hr_critical_sleep
            and bio.sleep.stage in ("deep", "light", "rem")
            and bio.heart_rate.last_update > now - 120
            and self._check_cooldown("critical_hr_sleep", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": (f"睡眠中に心拍数が{bio.heart_rate.bpm}bpmに達しています！体調を確認してください！"),
                        "zone": "home",
                        "tone": "alert",
                    },
                }
            )

        return actions
