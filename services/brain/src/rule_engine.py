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
from rules.gas import GasRulesMixin
from rules.home import HomeRulesMixin
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
        """Evaluate rules against current world state. Returns list of tool call actions."""
        actions = []
        now = time.time()

        for zone_id, zone in world_model.zones.items():
            env = zone.environment

            # CO2 above threshold -> create ventilation task
            if env.co2 is not None and env.co2 > self.thresholds.co2_high:
                if self._check_cooldown(f"co2_{zone_id}", now):
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"{zone_id}の換気",
                                "description": f"CO2濃度が{int(env.co2)}ppmです。窓を開けて換気してください。",
                                "urgency": 3,
                                "zone": zone_id,
                                "task_type": ["ventilation"],
                            },
                        }
                    )

            # Temperature too high or too low
            if env.temperature is not None:
                if env.temperature > self.thresholds.temp_high and self._check_cooldown(f"temp_high_{zone_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{zone_id}の室温が{env.temperature:.1f}度です。エアコンをつけましょう。",
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        }
                    )
                elif env.temperature < self.thresholds.temp_low and self._check_cooldown(f"temp_low_{zone_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{zone_id}の室温が{env.temperature:.1f}度と低めです。暖房をつけましょう。",
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        }
                    )

            # Sedentary detection (from events)
            for event in zone.events:
                if event.event_type == "sedentary_alert" and self._check_cooldown(f"sed_{zone_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": "長時間座っていますね。少し休憩しましょう。",
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        }
                    )

            # Long static posture detection
            occ = zone.occupancy
            if (
                occ.posture_status == "static"
                and occ.posture_duration_sec > self.thresholds.sedentary_minutes * 60
                and self._check_cooldown(f"posture_{zone_id}", now)
            ):
                duration_min = int(occ.posture_duration_sec / 60)
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"同じ姿勢で{duration_min}分経っています。少しストレッチしましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )

            # Humidity high
            if env.humidity is not None and env.humidity > self.thresholds.humidity_high:
                if self._check_cooldown(f"humidity_high_{zone_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{zone_id}の湿度が{env.humidity:.0f}%です。除湿しましょう。",
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        }
                    )

            # Humidity low
            if env.humidity is not None and env.humidity < self.thresholds.humidity_low:
                if self._check_cooldown(f"humidity_low_{zone_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{zone_id}の湿度が{env.humidity:.0f}%と低めです。加湿しましょう。",
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        }
                    )

            # Pressure drop detection (weather pain / 気象病)
            if env.pressure is not None:
                prev_pressure = self._pressure_history.get(zone_id)
                self._pressure_history[zone_id] = env.pressure
                if prev_pressure is not None and prev_pressure - env.pressure >= 5:
                    if self._check_cooldown(f"pressure_drop_{zone_id}", now):
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"気圧が低下しています（{prev_pressure:.0f}→{env.pressure:.0f}hPa）。頭痛に注意してください。",
                                    "zone": zone_id,
                                    "tone": "caring",
                                },
                            }
                        )

                # Sustained low pressure → weather headache warning (≤1 per day)
                if env.pressure < self.thresholds.low_pressure_threshold:
                    start = self._low_pressure_since.get(zone_id)
                    if start is None:
                        self._low_pressure_since[zone_id] = now
                    elif now - start >= self.thresholds.low_pressure_sustain_s and self._check_cooldown_daily(
                        f"pressure_low_sustained_{zone_id}", now
                    ):
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"気圧が{env.pressure:.0f}hPaで長時間低めです。気象病や頭痛に注意してください。",
                                    "zone": zone_id,
                                    "tone": "caring",
                                },
                            }
                        )
                else:
                    self._low_pressure_since.pop(zone_id, None)

            # Soil moisture watering (watering-gap-04 P1.4)
            if env.soil_moisture is not None and env.soil_moisture < self.thresholds.soil_moisture_low:
                if self._check_cooldown_custom(f"soil_low_{zone_id}", now, 6 * 3600):
                    pump = next(
                        (
                            d
                            for d in self._device_cache
                            if "pulse" in (d.get("capabilities") or [])
                            and any(
                                w in ((d.get("purpose") or "") + (d.get("device_id") or "")).lower()
                                for w in ("pump", "ポンプ", "water", "水や", "給水")
                            )
                            and (not d.get("zone") or d["zone"] == zone_id)
                        ),
                        None,
                    )
                    msg = f"植物の土壌水分が{env.soil_moisture:.0f}%です。水やりをしてください。"
                    if self.thresholds.auto_water_enabled and pump is not None:
                        actions.append(
                            self._make_action(
                                pump["device_id"],
                                "pulse",
                                {"duration_s": self.thresholds.auto_water_duration_s},
                            )
                        )
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"土壌水分が{env.soil_moisture:.0f}%だったので、自動で給水しました。",
                                    "zone": zone_id,
                                    "tone": "caring",
                                },
                            }
                        )
                    else:
                        actions.append(
                            {
                                "tool": "create_task",
                                "args": {
                                    "title": "植物に水やり",
                                    "description": msg,
                                    "urgency": 2,
                                    "zone": zone_id,
                                    "task_type": ["gardening"],
                                },
                            }
                        )
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": msg,
                                    "zone": zone_id,
                                    "tone": "caring",
                                },
                            }
                        )

            # VOC sustained high (wiring-gap-04 P1.5)
            if env.voc is not None:
                if env.voc > self.thresholds.voc_high_threshold:
                    start = self._voc_high_since.get(zone_id)
                    if start is None:
                        self._voc_high_since[zone_id] = now
                    elif now - start >= self.thresholds.voc_sustain_seconds and self._check_cooldown_custom(
                        f"voc_high_{zone_id}", now, self.thresholds.voc_cooldown_seconds
                    ):
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"VOCが{env.voc:.0f}と高めです。換気をおすすめします。",
                                    "zone": zone_id,
                                    "tone": "caring",
                                },
                            }
                        )
                        # Engage a ventilation scene if one exists
                        vent = next(
                            (
                                d
                                for d in self._device_cache
                                if any(
                                    w in (d.get("device_id") or "").lower() or w in (d.get("purpose") or "").lower()
                                    for w in ("vent", "換気", "fan", "ventilation")
                                )
                                and d.get("device_class") in ("switch", "fan")
                            ),
                            None,
                        )
                        if vent is not None:
                            actions.append(self._make_action(vent["device_id"], "on"))
                else:
                    self._voc_high_since.pop(zone_id, None)

            # Native PM2.5 high (wiring-gap-04 P1.6)
            # Dedup key is shared with zigbee HA-binary PM2.5 rule so both paths
            # can't fire the same message twice.
            if env.pm25 is not None and env.pm25 > self.thresholds.pm25_native_high:
                if self._check_cooldown(f"zigbee_pm25_{zone_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"PM2.5が{env.pm25:.0f}μg/m³です。空気清浄機をつけます。",
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        }
                    )
                    for d in self._get_devices(device_class="switch"):
                        did = (d.get("device_id") or "").lower()
                        purpose = (d.get("purpose") or "").lower()
                        if any(w in did or w in purpose for w in ("purifier", "清浄", "air")):
                            actions.append(self._make_action(d["device_id"], "on"))

            # Illuminance anomalies (wiring-gap-04 P1.8)
            if env.light is not None:
                hour = datetime.now().hour
                is_night = hour >= 22 or hour < 5
                # Sustained darkness outside sleeping hours → sensor / power fault suspicion
                if not is_night and env.light < self.thresholds.illuminance_low_lx:
                    start = self._low_light_since.get(zone_id)
                    if start is None:
                        self._low_light_since[zone_id] = now
                    elif now - start >= self.thresholds.illuminance_low_sustain_s and self._check_cooldown_daily(
                        f"light_low_sustained_{zone_id}", now
                    ):
                        actions.append(
                            {
                                "tool": "create_task",
                                "args": {
                                    "title": f"{zone_id}の照度センサー確認",
                                    "description": (
                                        f"日中に照度が{env.light:.0f}lxと低い状態が続いています。"
                                        "センサー故障または停電の可能性を確認してください。"
                                    ),
                                    "urgency": 2,
                                    "zone": zone_id,
                                    "task_type": ["maintenance"],
                                },
                            }
                        )
                else:
                    self._low_light_since.pop(zone_id, None)

                # Sustained daylight glare → suggest / request curtain close
                if env.light > self.thresholds.illuminance_high_lx:
                    start = self._high_light_since.get(zone_id)
                    if start is None:
                        self._high_light_since[zone_id] = now
                    elif now - start >= self.thresholds.illuminance_high_sustain_s and self._check_cooldown_custom(
                        f"light_high_sustained_{zone_id}", now, 3600
                    ):
                        covers = self._get_devices(device_class="cover", zone=zone_id)
                        if covers:
                            for c in covers:
                                actions.append(self._make_action(c["device_id"], "set_position", {"position": 0}))
                            actions.append(
                                {
                                    "tool": "speak",
                                    "args": {
                                        "message": "日差しが強いのでカーテンを閉めます。",
                                        "zone": zone_id,
                                        "tone": "neutral",
                                    },
                                }
                            )
                else:
                    self._high_light_since.pop(zone_id, None)

            # Late night low activity — suggest sleep
            hour = datetime.now().hour
            if (
                (hour >= 23 or hour < 5)
                and occ.activity_class == "idle"
                and occ.count > 0
                and self._check_cooldown(f"late_idle_{zone_id}", now)
            ):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "深夜ですね。そろそろ休みましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )

        # --- PC rules ---
        pc = world_model.pc_state
        if pc.gpu.temp_c > self.thresholds.pc_gpu_temp_high and self._check_cooldown("pc_gpu_hot", now):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"GPU温度が{pc.gpu.temp_c:.0f}度です。負荷を下げてください。",
                        "zone": "pc",
                        "tone": "alert",
                    },
                }
            )

        if pc.disk.partitions:
            for p in pc.disk.partitions:
                if p.percent > self.thresholds.pc_disk_high and self._check_cooldown(f"pc_disk_{p.mount}", now):
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"ディスク容量不足: {p.mount}",
                                "description": f"{p.mount}の使用率が{p.percent:.0f}%です。不要ファイルを削除してください。",
                                "urgency": 2,
                                "zone": "pc",
                                "task_type": ["maintenance"],
                            },
                        }
                    )

        # --- Device battery / link quality / last_seen rules (B-5) ---
        actions.extend(self._evaluate_device_health_rules(now))

        # --- Service VIP event rules (B-2) ---
        actions.extend(self._evaluate_service_vip_rules(world_model, now))

        # --- VLM swap stuck rule (B-3) ---
        if getattr(world_model, "vlm_model_swap_active", False):
            stats = getattr(world_model, "vlm_swap_stats", {})
            start = stats.get("last_swap_start_ts", 0)
            if start > 0 and (now - start) > 60 and self._check_cooldown_custom("vlm_swap_stuck", now, 1800):
                duration = int(now - start)
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": "VLM切替が長時間スタック",
                            "description": f"VLMモデル切替が{duration}秒継続しています。perception コンテナのログを確認してください。",
                            "urgency": 2,
                            "zone": "system",
                            "task_type": ["maintenance"],
                        },
                    }
                )

        # --- Heavy process rules (B-1) ---
        # CPU sustained > 90% for 5min, or single process > 4GB memory
        seen_names: set[str] = set()
        if pc.top_processes:
            for proc in pc.top_processes:
                if not proc.name:
                    continue
                seen_names.add(proc.name)
                # Skip dev-environment noise (Chrome, Slack, VS Code, etc.)
                pname_lower = proc.name.lower()
                if any(ex in pname_lower for ex in self.thresholds.pc_proc_heavy_exclude):
                    continue
                # CPU sustained
                if proc.cpu_percent >= self.thresholds.pc_proc_cpu_high:
                    start = self._heavy_proc_since.setdefault(proc.name, now)
                    if now - start >= self.thresholds.pc_proc_cpu_sustain_s and self._check_cooldown_custom(
                        f"pc_proc_cpu_{proc.name}", now, self.thresholds.pc_proc_cooldown_s
                    ):
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"{proc.name} がCPUを{proc.cpu_percent:.0f}%占有しています。閉じても大丈夫ですか？",
                                    "zone": "pc",
                                    "tone": "alert",
                                },
                            }
                        )
                else:
                    self._heavy_proc_since.pop(proc.name, None)
                # Memory single-process
                mem_gb = proc.mem_mb / 1024.0
                if mem_gb >= self.thresholds.pc_proc_mem_high_gb and self._check_cooldown_custom(
                    f"pc_proc_mem_{proc.name}", now, self.thresholds.pc_proc_cooldown_s
                ):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{proc.name} が{mem_gb:.1f}GBメモリを使っています。再起動を検討してください。",
                                "zone": "pc",
                                "tone": "caring",
                            },
                        }
                    )
        # GC: process names that disappeared from the top list, including
        # when the top-process payload is now empty.
        for stale in [n for n in self._heavy_proc_since if n not in seen_names]:
            self._heavy_proc_since.pop(stale, None)

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

        # --- Screen time rule ---
        st = world_model.user.screen_time
        if st.total_minutes >= self.thresholds.screen_time_alert_minutes and self._check_cooldown(
            "screen_time_alert", now
        ):
            hours = st.total_minutes // 60
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"画面を{hours}時間以上見ています。目を休めましょう。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

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
