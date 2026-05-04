"""
Rule-based fallback engine for HEMS Brain.
Used when GPU load is high or LLM is unavailable.
Evaluates simple threshold rules and returns tool call actions.
"""

import os
import random
import subprocess
import time
from datetime import UTC, datetime

from loguru import logger

from brain_utils import parse_iso_ts
from world_model.world_model import (
    BODY_TEMP_HIGH,
    CO2_CRITICAL,
    CO2_HIGH,
    HRV_LOW,
    HUMIDITY_HIGH,
    HUMIDITY_LOW,
    PC_DISK_HIGH,
    PC_GPU_TEMP_HIGH,
    PM25_HIGH,
    POWER_IDLE_WATTS,
    RESPIRATORY_RATE_HIGH,
    SCREEN_TIME_ALERT_MINUTES,
    SEDENTARY_MINUTES,
    TEMP_HIGH,
    TEMP_LOW,
)

# Critical thresholds used only in low-power mode (more extreme than normal alerts)
TEMP_CRITICAL_HIGH = float(os.getenv("HEMS_THRESHOLD_TEMP_CRITICAL_HIGH", "40.0"))
TEMP_CRITICAL_LOW = float(os.getenv("HEMS_THRESHOLD_TEMP_CRITICAL_LOW", "5.0"))
SPO2_CRITICAL_LOW = int(os.getenv("HEMS_THRESHOLD_SPO2_CRITICAL_LOW", "88"))
HR_CRITICAL_SLEEP = int(os.getenv("HEMS_THRESHOLD_HR_CRITICAL_SLEEP", "150"))
from schedule_learner import ScheduleLearner

# Biometric stale data detection (minutes without update before alerting)
BIOMETRIC_STALE_MINUTES = int(os.getenv("HEMS_BIOMETRIC_STALE_MINUTES", "30"))

# Heavy process thresholds (B-1)
PC_PROC_CPU_HIGH = float(os.getenv("HEMS_PROC_CPU_HIGH", "90"))
PC_PROC_CPU_SUSTAIN_S = int(os.getenv("HEMS_PROC_CPU_SUSTAIN_S", "300"))  # 5 min
PC_PROC_MEM_HIGH_GB = float(os.getenv("HEMS_PROC_MEM_HIGH_GB", "4.0"))
PC_PROC_COOLDOWN_S = int(os.getenv("HEMS_PROC_COOLDOWN_S", "1800"))  # 30 min per process
# Comma-separated process name substrings to exclude (case-insensitive). Useful in dev where
# Chrome / Slack / VS Code routinely sit at high CPU and would generate false positives.
PC_PROC_HEAVY_EXCLUDE = [
    s.strip().lower()
    for s in os.getenv("HEMS_PROC_HEAVY_EXCLUDE", "").split(",")
    if s.strip()
]

# Device health thresholds (B-5)
DEVICE_BATTERY_LOW = int(os.getenv("HEMS_DEVICE_BATTERY_LOW", "10"))  # %
DEVICE_LQI_LOW = int(os.getenv("HEMS_DEVICE_LQI_LOW", "50"))  # Z2M LQI 0-255
DEVICE_STALE_HOURS = int(os.getenv("HEMS_DEVICE_STALE_HOURS", "24"))  # hours since last_seen

GPU_TYPE = os.getenv("GPU_TYPE", "none")  # amd | nvidia | none
GPU_HIGH_LOAD_THRESHOLD = int(os.getenv("GPU_HIGH_LOAD_THRESHOLD", "80"))

# Sensor utilization thresholds (wiring-gap-04)
SOIL_MOISTURE_LOW = float(os.getenv("HEMS_THRESHOLD_SOIL_LOW", "25"))
AUTO_WATER_ENABLED = os.getenv("HEMS_ENABLE_AUTO_WATER", "false").lower() == "true"
AUTO_WATER_DURATION_S = min(int(os.getenv("HEMS_AUTO_WATER_DURATION_S", "45")), 45)
VOC_HIGH_THRESHOLD = float(os.getenv("HEMS_THRESHOLD_VOC_HIGH", "500"))
VOC_SUSTAIN_SECONDS = int(os.getenv("HEMS_VOC_SUSTAIN_SECONDS", "120"))
VOC_COOLDOWN_SECONDS = int(os.getenv("HEMS_VOC_COOLDOWN_SECONDS", "1800"))
PM25_NATIVE_HIGH = float(os.getenv("HEMS_THRESHOLD_PM25_NATIVE", "35"))
LOW_PRESSURE_THRESHOLD = float(os.getenv("HEMS_THRESHOLD_PRESSURE_LOW", "1000"))
LOW_PRESSURE_SUSTAIN_S = int(os.getenv("HEMS_PRESSURE_LOW_SUSTAIN_S", str(3 * 3600)))
ILLUMINANCE_LOW_LX = float(os.getenv("HEMS_THRESHOLD_LIGHT_LOW", "20"))
ILLUMINANCE_LOW_SUSTAIN_S = int(os.getenv("HEMS_LIGHT_LOW_SUSTAIN_S", "600"))
ILLUMINANCE_HIGH_LX = float(os.getenv("HEMS_THRESHOLD_LIGHT_HIGH", "50000"))
ILLUMINANCE_HIGH_SUSTAIN_S = int(os.getenv("HEMS_LIGHT_HIGH_SUSTAIN_S", "600"))

# Absence lighting config
ABSENCE_LIGHTING_ENABLED = os.getenv("HEMS_ABSENCE_LIGHTING_ENABLED", "true").lower() == "true"
ABSENCE_LIGHTING_INTERVAL = int(os.getenv("HEMS_ABSENCE_LIGHTING_INTERVAL", "1800"))
ABSENCE_LIGHTING_START_HOUR = int(os.getenv("HEMS_ABSENCE_LIGHTING_HOURS_START", "17"))
ABSENCE_LIGHTING_END_HOUR = int(os.getenv("HEMS_ABSENCE_LIGHTING_HOURS_END", "23"))

# Circadian lighting config
CIRCADIAN_ENABLED = os.getenv("HEMS_CIRCADIAN_ENABLED", "true").lower() == "true"
CIRCADIAN_INTERVAL = int(os.getenv("HEMS_CIRCADIAN_INTERVAL", "1800"))

# Circadian color temp curve (hour → mirek, brightness_pct)
# 153 mirek = 6500K (cold), 500 mirek = 2000K (warm)
CIRCADIAN_CURVE = [
    (0, 450, 30),  # midnight: very warm, dim
    (6, 400, 50),  # early morning: warm
    (8, 270, 100),  # morning: cool/energizing
    (12, 250, 100),  # noon: daylight
    (17, 300, 100),  # afternoon: neutral
    (20, 380, 80),  # evening: warm
    (22, 430, 50),  # late evening: very warm, dim
]


def _get_gpu_utilization() -> float | None:
    """Query GPU utilization percentage. Returns None if unavailable."""
    try:
        if GPU_TYPE == "nvidia":
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                timeout=5,
                text=True,
            )
            return float(out.strip().split("\n")[0])
        elif GPU_TYPE == "amd":
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


class RuleEngine:
    """Threshold-based decision engine — no LLM required."""

    COOLDOWN_SECONDS = 300  # 5 minutes

    def __init__(self, schedule_learner: ScheduleLearner | None = None, mqtt_publisher=None):
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

            # CO2 above threshold -> create ventilation task
            if env.co2 is not None and env.co2 > CO2_HIGH:
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
                if env.temperature > TEMP_HIGH and self._check_cooldown(f"temp_high_{zone_id}", now):
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
                elif env.temperature < TEMP_LOW and self._check_cooldown(f"temp_low_{zone_id}", now):
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
                and occ.posture_duration_sec > SEDENTARY_MINUTES * 60
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
            if env.humidity is not None and env.humidity > HUMIDITY_HIGH:
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
            if env.humidity is not None and env.humidity < HUMIDITY_LOW:
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
                if env.pressure < LOW_PRESSURE_THRESHOLD:
                    start = self._low_pressure_since.get(zone_id)
                    if start is None:
                        self._low_pressure_since[zone_id] = now
                    elif now - start >= LOW_PRESSURE_SUSTAIN_S and self._check_cooldown_daily(
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
            if env.soil_moisture is not None and env.soil_moisture < SOIL_MOISTURE_LOW:
                if self._check_cooldown_custom(
                    f"soil_low_{zone_id}", now, 6 * 3600
                ):
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
                    msg = (
                        f"植物の土壌水分が{env.soil_moisture:.0f}%です。水やりをしてください。"
                    )
                    if AUTO_WATER_ENABLED and pump is not None:
                        actions.append(
                            self._make_action(
                                pump["device_id"],
                                "pulse",
                                {"duration_s": AUTO_WATER_DURATION_S},
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
                if env.voc > VOC_HIGH_THRESHOLD:
                    start = self._voc_high_since.get(zone_id)
                    if start is None:
                        self._voc_high_since[zone_id] = now
                    elif now - start >= VOC_SUSTAIN_SECONDS and self._check_cooldown_custom(
                        f"voc_high_{zone_id}", now, VOC_COOLDOWN_SECONDS
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
                                    w in (d.get("device_id") or "").lower()
                                    or w in (d.get("purpose") or "").lower()
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
            if env.pm25 is not None and env.pm25 > PM25_NATIVE_HIGH:
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
                if not is_night and env.light < ILLUMINANCE_LOW_LX:
                    start = self._low_light_since.get(zone_id)
                    if start is None:
                        self._low_light_since[zone_id] = now
                    elif now - start >= ILLUMINANCE_LOW_SUSTAIN_S and self._check_cooldown_daily(
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
                if env.light > ILLUMINANCE_HIGH_LX:
                    start = self._high_light_since.get(zone_id)
                    if start is None:
                        self._high_light_since[zone_id] = now
                    elif now - start >= ILLUMINANCE_HIGH_SUSTAIN_S and self._check_cooldown_custom(
                        f"light_high_sustained_{zone_id}", now, 3600
                    ):
                        covers = self._get_devices(device_class="cover", zone=zone_id)
                        if covers:
                            for c in covers:
                                actions.append(
                                    self._make_action(
                                        c["device_id"], "set_position", {"position": 0}
                                    )
                                )
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
        if pc.gpu.temp_c > PC_GPU_TEMP_HIGH and self._check_cooldown("pc_gpu_hot", now):
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
                if p.percent > PC_DISK_HIGH and self._check_cooldown(f"pc_disk_{p.mount}", now):
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
            if start > 0 and (now - start) > 60 and self._check_cooldown_custom(
                "vlm_swap_stuck", now, 1800
            ):
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
        if pc.top_processes:
            seen_names: set[str] = set()
            for proc in pc.top_processes:
                if not proc.name:
                    continue
                seen_names.add(proc.name)
                # Skip dev-environment noise (Chrome, Slack, VS Code, etc.)
                pname_lower = proc.name.lower()
                if any(ex in pname_lower for ex in PC_PROC_HEAVY_EXCLUDE):
                    continue
                # CPU sustained
                if proc.cpu_percent >= PC_PROC_CPU_HIGH:
                    start = self._heavy_proc_since.setdefault(proc.name, now)
                    if now - start >= PC_PROC_CPU_SUSTAIN_S and self._check_cooldown_custom(
                        f"pc_proc_cpu_{proc.name}", now, PC_PROC_COOLDOWN_S
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
                if mem_gb >= PC_PROC_MEM_HIGH_GB and self._check_cooldown_custom(
                    f"pc_proc_mem_{proc.name}", now, PC_PROC_COOLDOWN_S
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
            # GC: process names that disappeared from the top list
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
        if st.total_minutes >= SCREEN_TIME_ALERT_MINUTES and self._check_cooldown("screen_time_alert", now):
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

    def _evaluate_gas_rules(self, gas, now: float, world_model=None) -> list[dict]:
        """Evaluate GAS-related rules. Returns list of tool call actions."""
        actions = []

        try:
            local_now = datetime.now()
        except Exception:
            local_now = datetime.now(UTC)
        hour = local_now.hour
        weekday = local_now.weekday()  # 0=Monday, 6=Sunday

        # --- Calendar rules ---

        # 1. Meeting reminder — 10 min before event
        for ev in gas.calendar_events:
            if ev.is_all_day or ev.start_ts <= 0:
                continue
            minutes_until = (ev.start_ts - now) / 60
            if 0 < minutes_until <= 10:
                key = f"gas_meeting_remind_{ev.id}"
                if self._check_cooldown(key, now):
                    msg = f"あと{int(minutes_until)}分で「{ev.title}」が始まります。"
                    if ev.location:
                        msg += f"（{ev.location}）"
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {"message": msg[:70], "zone": "home", "tone": "alert"},
                        }
                    )

        # 1b. Meeting prep — 30 min before event (speak + dim lights + 静音推奨)
        for ev in gas.calendar_events:
            if ev.is_all_day or ev.start_ts <= 0:
                continue
            minutes_until = (ev.start_ts - now) / 60
            # 25-30 min window so the rule fires reliably even with 30s cycle
            if 25 < minutes_until <= 30:
                key = f"gas_meeting_prep_{ev.id}"
                if self._check_cooldown_custom(key, now, 3600):
                    msg = f"30分後に「{ev.title}」があります。準備をお勧めします。"
                    if ev.location:
                        msg += f"（{ev.location}）"
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {"message": msg[:70], "zone": "home", "tone": "caring"},
                        }
                    )
                    # Dim lights to 70% in any zone with active light to encourage focus.
                    # Cap at first 2 lights to avoid wholesale changes.
                    dimmed = 0
                    for d in self._device_cache:
                        if dimmed >= 2:
                            break
                        caps = d.get("capabilities") or []
                        if "set_brightness" not in caps:
                            continue
                        if not d.get("is_enabled", True):
                            continue
                        last_state = d.get("last_state") or {}
                        if not last_state.get("on"):
                            continue
                        actions.append(
                            self._make_action(
                                d["device_id"],
                                "set_brightness",
                                {"brightness": 178},  # 70% of 255
                            )
                        )
                        dimmed += 1

        # 2. Overlapping events detection
        timed_events = [e for e in gas.calendar_events if not e.is_all_day and e.start_ts > 0]
        for i, ev1 in enumerate(timed_events):
            for ev2 in timed_events[i + 1 :]:
                if ev1.start_ts < ev2.end_ts and ev2.start_ts < ev1.end_ts:
                    key = f"gas_overlap_{ev1.id}_{ev2.id}"
                    if self._check_cooldown(key, now):
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"予定が重複しています: 「{ev1.title}」と「{ev2.title}」",
                                    "zone": "home",
                                    "tone": "alert",
                                },
                            }
                        )

        # 3. Morning briefing — 8:00-9:00, once per day
        if 8 <= hour < 9 and self._check_cooldown_daily("gas_morning_brief", now):
            event_count = len(gas.calendar_events)
            pending_tasks = [t for t in gas.tasks if t.status != "completed"]
            overdue = [t for t in gas.tasks if t.is_overdue]
            inbox = gas.gmail_labels.get("INBOX")
            unread = inbox.unread if inbox else 0
            msg = f"おはようございます。今日の予定{event_count}件"
            if pending_tasks:
                msg += f"、タスク{len(pending_tasks)}件"
            if overdue:
                msg += f"（期限切れ{len(overdue)}件）"
            if unread > 0:
                msg += f"、未読{unread}通"
            msg += "です。"
            actions.append(
                {
                    "tool": "speak",
                    "args": {"message": msg[:70], "zone": "home", "tone": "neutral"},
                }
            )

        # 4. Evening summary — 21:00-22:00, once per day
        if 21 <= hour < 22 and self._check_cooldown_daily("gas_evening_summary", now):
            # Look for tomorrow's first event
            tomorrow_start = now + (24 - hour) * 3600
            tomorrow_end = tomorrow_start + 24 * 3600
            tomorrow_events = [
                e for e in gas.calendar_events if not e.is_all_day and tomorrow_start <= e.start_ts < tomorrow_end
            ]
            if tomorrow_events:
                first = tomorrow_events[0]
                t_str = first.start.split("T")[1][:5] if "T" in first.start else "?"
                msg = f"明日は{len(tomorrow_events)}件の予定があります。最初は{t_str}「{first.title}」です。"
            else:
                msg = "明日の予定はありません。ゆっくり休んでください。"
            actions.append(
                {
                    "tool": "speak",
                    "args": {"message": msg[:70], "zone": "home", "tone": "caring"},
                }
            )

        # 5. Long free slot detection — 9:00-18:00, 2h+ free slots
        if 9 <= hour < 18:
            long_slots = [s for s in gas.free_slots if s.duration_minutes >= 120]
            for slot in long_slots[:1]:  # Only notify about first long slot
                key = f"gas_free_slot_{slot.start[:13]}"
                if self._check_cooldown(key, now):
                    t_str = slot.start.split("T")[1][:5] if "T" in slot.start else "?"
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{t_str}から{slot.duration_minutes}分の空き時間があります。集中作業に最適です。",
                                "zone": "home",
                                "tone": "neutral",
                            },
                        }
                    )

        # 6. Early bedtime suggestion — tomorrow's first event before 8:00
        if hour == 22:
            tomorrow_start = now + 2 * 3600  # ~midnight
            early_cutoff = tomorrow_start + 8 * 3600  # ~8:00 tomorrow
            early_events = [
                e for e in gas.calendar_events if not e.is_all_day and tomorrow_start <= e.start_ts < early_cutoff
            ]
            if early_events and self._check_cooldown_daily("gas_early_bed", now):
                first = early_events[0]
                t_str = first.start.split("T")[1][:5] if "T" in first.start else "?"
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"明日は{t_str}に予定があります。早めに休みましょう。",
                            "zone": "home",
                            "tone": "caring",
                        },
                    }
                )

        # --- Task rules ---

        # 7. Overdue task alert — staged escalation
        overdue_tasks = [t for t in gas.tasks if t.is_overdue]
        if overdue_tasks:
            # Stage A — initial info speak (1 per day, summary)
            if self._check_cooldown_daily("gas_overdue_alert", now):
                names = ", ".join(t.title[:15] for t in overdue_tasks[:3])
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"期限切れのタスクが{len(overdue_tasks)}件あります: {names}",
                            "zone": "home",
                            "tone": "alert",
                        },
                    }
                )

            # Stage B/C — per-task escalation based on hours overdue
            from datetime import datetime as _dt

            for task in overdue_tasks:
                if not task.due or not task.id:
                    continue
                try:
                    due_dt = _dt.fromisoformat(task.due.replace("Z", "+00:00"))
                    hours_overdue = (now - due_dt.timestamp()) / 3600
                except (ValueError, AttributeError):
                    continue

                # Stage B (≥24h overdue): bump priority, alert
                if hours_overdue >= 24:
                    key_b = f"gas_overdue_24h_{task.id}"
                    if self._check_cooldown_custom(key_b, now, 86400):
                        actions.append(
                            {
                                "tool": "create_task",
                                "args": {
                                    "title": f"【優先】期限超過 {int(hours_overdue / 24)}日: {task.title[:40]}",
                                    "description": (
                                        f"Googleタスク「{task.title}」が{int(hours_overdue)}時間超過しています。"
                                        f"対応または再スケジュールを検討してください。"
                                    ),
                                    "urgency": 4,
                                    "zone": "home",
                                    "task_type": ["overdue_escalation"],
                                },
                            }
                        )

                # Stage C (≥72h overdue): suggest deletion
                if hours_overdue >= 72:
                    key_c = f"gas_overdue_72h_{task.id}"
                    if self._check_cooldown_custom(key_c, now, 7 * 86400):
                        actions.append(
                            {
                                "tool": "create_task",
                                "args": {
                                    "title": f"【削除候補】3日超過: {task.title[:40]}",
                                    "description": (
                                        f"「{task.title}」が72時間以上超過。実施意志がない場合は削除を検討。"
                                    ),
                                    "urgency": 2,
                                    "zone": "home",
                                    "task_type": ["delete_candidate"],
                                },
                            }
                        )

        # 8. Daily task sync — 8:00-10:00, sync Google Tasks to HEMS tasks
        if 8 <= hour < 10 and self._check_cooldown_daily("gas_task_sync", now):
            pending = [t for t in gas.tasks if t.status != "completed" and t.due]
            for task in pending[:3]:
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": f"[Google] {task.title}",
                            "description": f"Google Tasks: {task.notes}"
                            if task.notes
                            else f"Google Tasksから同期: {task.title}",
                            "urgency": 3 if task.is_overdue else 2,
                            "zone": "home",
                            "task_type": ["google_tasks"],
                        },
                    }
                )

        # --- Gmail rules ---

        inbox = gas.gmail_labels.get("INBOX")
        if inbox:
            # 9. Unread alert — 10+ unread
            if inbox.unread >= 10 and self._check_cooldown("gas_gmail_unread", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"未読メールが{inbox.unread}通あります。確認しましょう。",
                            "zone": "home",
                            "tone": "neutral",
                        },
                    }
                )

            # 10. Unread critical — 20+ unread
            if inbox.unread >= 20 and self._check_cooldown("gas_gmail_critical", now):
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": "メール整理",
                            "description": f"未読メールが{inbox.unread}通溜まっています。整理してください。",
                            "urgency": 2,
                            "zone": "home",
                            "task_type": ["email"],
                        },
                    }
                )

        # --- Drive rules ---

        # 11. Document update notification
        doc_types = {
            "application/vnd.google-apps.document": "ドキュメント",
            "application/vnd.google-apps.spreadsheet": "スプレッドシート",
            "application/vnd.google-apps.presentation": "スライド",
        }
        for f in gas.drive_recent[:5]:
            if f.mime_type in doc_types:
                key = f"gas_drive_{f.name[:20]}_{f.modified_time[:10]}"
                if self._check_cooldown(key, now):
                    type_name = doc_types[f.mime_type]
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{type_name}「{f.name[:20]}」が更新されました。",
                                "zone": "home",
                                "tone": "neutral",
                            },
                        }
                    )
                    break  # Only one drive notification per cycle

        # --- Sheets rules ---

        # 12. Threshold monitoring — sheets with metric/value/threshold columns
        for name, sheet in gas.sheets.items():
            if not sheet.headers or not sheet.values:
                continue
            headers_lower = [h.lower() for h in sheet.headers]
            try:
                metric_idx = next(i for i, h in enumerate(headers_lower) if h in ("metric", "項目", "name"))
                value_idx = next(i for i, h in enumerate(headers_lower) if h in ("value", "値", "actual"))
                threshold_idx = next(i for i, h in enumerate(headers_lower) if h in ("threshold", "閾値", "limit"))
            except StopIteration:
                continue  # Sheet doesn't have required columns

            for row in sheet.values:
                if len(row) <= max(metric_idx, value_idx, threshold_idx):
                    continue
                try:
                    metric_name = str(row[metric_idx])
                    value = float(row[value_idx])
                    threshold = float(row[threshold_idx])
                except (ValueError, TypeError):
                    continue

                if value > threshold:
                    key = f"gas_sheet_{name}_{metric_name}"
                    if self._check_cooldown(key, now):
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"[{name}] {metric_name}が閾値超過: {value} > {threshold}",
                                    "zone": "home",
                                    "tone": "alert",
                                },
                            }
                        )

        # --- Weekly rules ---

        # 13. Weekly review — Sunday 18:00-20:00
        if weekday == 6 and 18 <= hour < 20:
            if self._check_cooldown_daily("gas_weekly_review", now):
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": "週次レビュー",
                            "description": "今週の振り返りと来週の計画を立てましょう。",
                            "urgency": 2,
                            "zone": "home",
                            "task_type": ["review"],
                        },
                    }
                )

        # Urgent news notification
        if hasattr(world_model, "news_state"):
            ns = world_model.news_state
            for article in ns.urgent_articles:
                url_key = article.get("url", "")[:50]
                if url_key and self._check_cooldown(f"news_urgent_{url_key}", now):
                    title = article.get("title", "")[:50]
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"速報です。{title}",
                                "zone": "home",
                                "tone": "alert",
                            },
                        }
                    )

        return actions

    def _evaluate_home_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate home automation rules (vendor-agnostic via Device Registry)."""
        actions = []
        hour = datetime.now().hour

        # --- 1. Sleep detection → lights off ---
        if hour >= 23 or hour < 5:
            for zone_id, zone in world_model.zones.items():
                occ = zone.occupancy
                if (
                    occ.count > 0
                    and occ.activity_class == "idle"
                    and occ.posture_status == "static"
                    and occ.posture_duration_sec > 600
                ):
                    lights_on = [d for d in self._get_devices(device_class="light") if self._device_is_on(d)]
                    if lights_on and self._check_cooldown_daily(f"ha_sleep_detect_{zone_id}", now):
                        for d in lights_on:
                            actions.append(self._make_action(d["device_id"], "off"))
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "おやすみなさい。照明を消しますね。",
                                    "zone": zone_id,
                                    "tone": "caring",
                                },
                            }
                        )

        # --- 2. Pre-arrival HVAC ---
        if self.schedule_learner:
            calendar_events = None
            if world_model.gas_state.bridge_connected:
                calendar_events = world_model.gas_state.calendar_events

            predicted_arrival = self.schedule_learner.predict_next_arrival(calendar_events)
            if predicted_arrival:
                minutes_until = (predicted_arrival - now) / 60
                # Multi-source "away" check (camera + PIR + motion + PC + HR)
                # so we don't pre-heat the house when the user is already home
                # but simply out of camera view.
                all_away = not world_model.is_anyone_home()

                if all_away and 0 < minutes_until <= 30:
                    if self._check_cooldown("ha_prearrival_hvac", now):
                        month = datetime.now().month
                        if 6 <= month <= 9:
                            mode, temp = "cool", 26
                        elif month <= 3 or month >= 11:
                            mode, temp = "heat", 22
                        else:
                            mode, temp = "auto", 24

                        for d in self._get_devices(device_class="climate"):
                            actions.append(self._make_action(d["device_id"], "set_temperature", {"value": temp, "mode": mode}))
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"もうすぐ帰宅ですね。エアコンを{mode}モード{temp}度でつけました。",
                                    "zone": "home",
                                    "tone": "caring",
                                },
                            }
                        )

        # --- 3. Wake-up curtain → natural light ---
        if self.schedule_learner:
            calendar_events = None
            if world_model.gas_state.bridge_connected:
                calendar_events = world_model.gas_state.calendar_events

            wake_time = self.schedule_learner.get_wake_time(calendar_events)
            if wake_time:
                minutes_until_wake = (wake_time - now) / 60
                if 0 < minutes_until_wake <= 60:
                    covers = self._get_devices(device_class="cover")
                    closed_covers = [d for d in covers if not (d.get("last_state") or {}).get("position", 0) > 0]
                    if closed_covers and self._check_cooldown_daily("ha_wake_curtain", now):
                        for d in closed_covers:
                            actions.append(self._make_action(d["device_id"], "set_position", {"value": 100}))

        # --- 4. Wake-up detection → lights on + morning greeting ---
        if 5 <= hour < 10:
            for zone_id, zone in world_model.zones.items():
                occ = zone.occupancy
                if (
                    occ.count > 0
                    and occ.activity_class in ("low", "moderate", "high")
                    and self._check_cooldown_daily(f"ha_wake_detect_{zone_id}", now)
                ):
                    lights_off = [d for d in self._get_devices(device_class="light") if not self._device_is_on(d)]
                    if lights_off:
                        for d in lights_off:
                            actions.append(self._make_action(d["device_id"], "on"))
                            actions.append(self._make_action(d["device_id"], "set_brightness", {"value": 255}))
                            if "color_temp" in (d.get("capabilities") or []):
                                actions.append(self._make_action(d["device_id"], "set_color_temp", {"value": 400}))
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": "おはようございます。",
                                "zone": zone_id,
                                "tone": "neutral",
                            },
                        }
                    )

        return actions

    def _evaluate_biometric_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate biometric health rules."""
        actions = []
        bio = world_model.biometric_state
        hour = datetime.now().hour

        # 0. Stale biometric data alert
        if (
            bio.bridge_connected
            and bio.last_update > 0
            and (now - bio.last_update) > BIOMETRIC_STALE_MINUTES * 60
            and self._check_cooldown("bio_stale_data", now)
        ):
            stale_minutes = int((now - bio.last_update) / 60)
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"バイオメトリクスデータが{stale_minutes}分間更新されていません。スマートバンドの接続を確認してください。",
                        "zone": "home",
                        "tone": "alert",
                    },
                }
            )

        # 1. High heart rate alert
        if bio.heart_rate.bpm is not None and bio.heart_rate.bpm > 120 and self._check_cooldown("bio_hr_high", now):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"心拍数が{bio.heart_rate.bpm}bpmです。少し休憩しましょう。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

        # 2. High stress alert
        if bio.stress.level > 80 and bio.stress.last_update > 0 and self._check_cooldown("bio_stress_high", now):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": "ストレスが高めです。深呼吸してリラックスしましょう。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )
            # Stress spike → request VLM scan (Wave 4.7) so we can confirm the
            # user is actually OK (e.g., not just sitting still elevated).
            # Only when MQTT publisher available; cooldown 30min via ad-hoc key.
            if self.mqtt_publisher is not None and self._check_cooldown_custom(
                "bio_stress_vlm_request", now, 1800
            ):
                try:
                    self.mqtt_publisher(
                        "hems/perception/vlm/request",
                        {"reason": "stress_spike", "stress_level": bio.stress.level},
                    )
                except Exception:
                    pass

        # 3. High fatigue alert
        if bio.fatigue.score > 70 and bio.fatigue.last_update > 0 and self._check_cooldown("bio_fatigue_high", now):
            if 21 <= hour <= 23:
                msg = "疲労が溜まっていますね。今日は早めに休みましょう。"
            else:
                msg = "疲れが溜まっていますね。少し休憩しましょう。"
            actions.append(
                {
                    "tool": "speak",
                    "args": {"message": msg, "zone": "home", "tone": "caring"},
                }
            )

        # 4. Poor sleep quality morning notification (8-10 AM)
        if (
            8 <= hour < 10
            and bio.sleep.quality_score > 0
            and bio.sleep.quality_score < 50
            and self._check_cooldown_daily("bio_sleep_poor", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"昨夜の睡眠品質が{bio.sleep.quality_score}点でした。今日は無理しないでくださいね。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

        # 5. Step goal achievement
        if (
            bio.activity.steps > 0
            and bio.activity.steps_goal > 0
            and bio.activity.steps >= bio.activity.steps_goal
            and self._check_cooldown_daily("bio_steps_goal", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"歩数{bio.activity.steps}歩で目標達成です！お疲れさまでした！",
                        "zone": "home",
                        "tone": "humorous",
                    },
                }
            )

        # 6. Enhanced sleep detection (biometric) → turn off lights
        if (
            bio.sleep.stage in ("deep", "light", "rem")
            and self._device_cache
            and self._check_cooldown_daily("bio_sleep_lights", now)
        ):
            lights_on = [d for d in self._get_devices(device_class="light") if self._device_is_on(d)]
            if lights_on:
                for d in lights_on:
                    actions.append(self._make_action(d["device_id"], "off"))
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "おやすみなさい。照明を消しますね。",
                            "zone": "home",
                            "tone": "caring",
                        },
                    }
                )

        # 8. Low HRV alert (autonomic stress)
        if (
            bio.hrv.rmssd_ms is not None
            and bio.hrv.rmssd_ms < HRV_LOW
            and bio.hrv.last_update > 0
            and self._check_cooldown("bio_hrv_low", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"HRVが{bio.hrv.rmssd_ms}msと低めです。自律神経の疲れが出ています。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

        # 9. Body temperature high
        if (
            bio.body_temperature.celsius is not None
            and bio.body_temperature.celsius > BODY_TEMP_HIGH
            and bio.body_temperature.last_update > 0
            and self._check_cooldown("bio_body_temp_high", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"体温が{bio.body_temperature.celsius:.1f}°Cです。体調に気をつけてください。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

        # 10. Respiratory rate high
        if (
            bio.respiratory_rate.breaths_per_minute is not None
            and bio.respiratory_rate.breaths_per_minute > RESPIRATORY_RATE_HIGH
            and bio.respiratory_rate.last_update > 0
            and self._check_cooldown("bio_resp_high", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": "呼吸が速くなっています。落ち着いて深呼吸しましょう。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

        # 11. Fatigue-linked dimming (21-23h, fatigue > 60)
        if (
            self._device_cache
            and 21 <= hour <= 23
            and bio.fatigue.score > 60
            and bio.fatigue.last_update > 0
            and self._check_cooldown("bio_fatigue_dim", now)
        ):
            for d in self._get_devices(device_class="light"):
                if self._device_is_on(d) and self._device_brightness(d) > 100:
                    actions.append(self._make_action(d["device_id"], "set_brightness", {"value": 80}))
                    if "color_temp" in (d.get("capabilities") or []):
                        actions.append(self._make_action(d["device_id"], "set_color_temp", {"value": 400}))

        # --- Trend rules (Wave 3.2) ---
        # Fatigue streak: 3 consecutive days fatigue >= 70 (sample at distinct days)
        actions.extend(self._evaluate_fatigue_streak(bio, now))
        # Sleep decline: 7-day quality drop -15% vs prior 7-day baseline
        actions.extend(self._evaluate_sleep_decline(bio, now))
        # Stress + HR coupling: 15min stress > 70 AND HR baseline +20%
        actions.extend(self._evaluate_stress_hr_coupling(bio, now))

        return actions

    def _evaluate_fatigue_streak(self, bio, now: float) -> list[dict]:
        """3 consecutive days with peak fatigue ≥ 70."""
        actions = []
        history = bio.history.get("fatigue") if bio.history else None
        if not history or len(history) < 3:
            return actions

        from datetime import datetime as _dt

        # Group samples by date (local), keep peak per day
        peaks_by_day: dict[str, float] = {}
        for ts, value in history:
            day = _dt.fromtimestamp(ts).strftime("%Y-%m-%d")
            peaks_by_day[day] = max(peaks_by_day.get(day, 0), value)

        # Need 3 most recent calendar days
        sorted_days = sorted(peaks_by_day.keys(), reverse=True)
        if len(sorted_days) < 3:
            return actions

        recent_3 = [peaks_by_day[d] for d in sorted_days[:3]]
        if all(v >= 70 for v in recent_3):
            if self._check_cooldown_daily("bio_fatigue_streak", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "3日連続で疲労度が高い状態が続いています。今日は早めに休んでください。",
                            "zone": "home",
                            "tone": "caring",
                        },
                    }
                )
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": "疲労蓄積アラート: 3日連続で疲労度70以上",
                            "description": (
                                f"直近3日の疲労度ピーク: {recent_3[0]:.0f}, {recent_3[1]:.0f}, {recent_3[2]:.0f}。"
                                f"休息計画の見直しを検討してください。"
                            ),
                            "urgency": 3,
                            "zone": "home",
                            "task_type": ["fatigue_streak"],
                        },
                    }
                )
        return actions

    def _evaluate_sleep_decline(self, bio, now: float) -> list[dict]:
        """7-day rolling sleep quality average vs prior 7-day baseline. Trigger if drop ≥ 15%."""
        actions = []
        history = bio.history.get("sleep_quality") if bio.history else None
        if not history or len(history) < 14:
            return actions

        recent = [v for _, v in list(history)[-7:]]
        prior = [v for _, v in list(history)[-14:-7]]
        if not recent or not prior:
            return actions

        avg_recent = sum(recent) / len(recent)
        avg_prior = sum(prior) / len(prior)
        if avg_prior < 30:  # baseline too noisy
            return actions

        decline_pct = (avg_prior - avg_recent) / avg_prior
        if decline_pct >= 0.15 and self._check_cooldown_custom("bio_sleep_decline", now, 3 * 86400):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": (
                            f"睡眠の質が直近7日で{int(decline_pct * 100)}%低下しています。"
                            f"就寝時刻や環境を見直しましょう。"
                        ),
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )
        return actions

    def _evaluate_stress_hr_coupling(self, bio, now: float) -> list[dict]:
        """15min sustained stress > 70 AND HR > resting baseline + 20%."""
        actions = []
        stress_hist = bio.history.get("stress") if bio.history else None
        hr_hist = bio.history.get("heart_rate") if bio.history else None
        if not stress_hist or not hr_hist:
            return actions

        cutoff_15min = now - 15 * 60
        recent_stress = [v for ts, v in stress_hist if ts >= cutoff_15min]
        recent_hr = [v for ts, v in hr_hist if ts >= cutoff_15min]

        if len(recent_stress) < 3 or len(recent_hr) < 3:
            return actions

        sustained_stress = sum(recent_stress) / len(recent_stress) > 70
        if not sustained_stress:
            return actions

        baseline_hr = bio.heart_rate.resting_bpm
        if not baseline_hr or baseline_hr <= 0:
            # Estimate baseline from HR history (lowest 10% over the window we have)
            all_hr = sorted(v for _, v in hr_hist)
            if len(all_hr) >= 10:
                baseline_hr = all_hr[len(all_hr) // 10]
            else:
                return actions

        avg_recent_hr = sum(recent_hr) / len(recent_hr)
        if avg_recent_hr >= baseline_hr * 1.2 and self._check_cooldown("bio_stress_hr_coupling", now):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": (
                            f"ストレスと心拍が連動して上昇しています。"
                            f"(平均ストレス{int(sum(recent_stress) / len(recent_stress))}, "
                            f"平均心拍{int(avg_recent_hr)}bpm)。深呼吸や休憩をどうぞ。"
                        ),
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )
        return actions

    def _evaluate_perception_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate camera/perception-based rules."""
        actions = []
        hour = datetime.now().hour
        ha_enabled = world_model.home_devices.bridge_connected

        for zone_id, zone in world_model.zones.items():
            occ = zone.occupancy

            # 1. Sedentary sitting detection (camera posture)
            # Require all three: sitting posture, ≥90min streak, activity<0.1.
            # The activity gate cuts false positives when the YOLO posture
            # classifier locks onto "sitting" but the user is actually moving
            # (reaching, typing, fidgeting).
            if (
                occ.posture == "sitting"
                and occ.posture_duration_sec >= 90 * 60
                and occ.activity_level < 0.1
                and self._check_cooldown(f"percep_sitting_{zone_id}", now)
            ):
                duration_min = int(occ.posture_duration_sec / 60)
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"{duration_min}分座りっぱなしです。少し体を動かしましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )

            # 2. Empty room with lights/climate on → turn off
            has_devs = ha_enabled or bool(self._device_cache)
            if has_devs and occ.count == 0 and occ.last_update > 0 and now - occ.last_update < 300:
                lights_on = [d for d in self._get_devices(device_class="light", zone=zone_id) if self._device_is_on(d)]
                if lights_on and self._check_cooldown(f"percep_empty_lights_{zone_id}", now):
                    for d in lights_on:
                        actions.append(self._make_action(d["device_id"], "off"))
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{zone_id}は空室です。照明を消しますね。",
                                "zone": zone_id,
                                "tone": "neutral",
                            },
                        }
                    )
                climates_on = [d for d in self._get_devices(device_class="climate", zone=zone_id)
                               if (d.get("last_state") or {}).get("hvac_mode", "off") != "off"]
                if climates_on and self._check_cooldown(f"percep_empty_climate_{zone_id}", now):
                    for d in climates_on:
                        actions.append(self._make_action(d["device_id"], "set_temperature", {"mode": "off"}))

            # 3. Daytime lying detection → health check
            if (
                6 <= hour <= 21
                and occ.posture == "lying"
                and occ.posture_duration_sec > 600
                and self._check_cooldown(f"percep_lying_{zone_id}", now)
            ):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "日中に横になっていますね。体調は大丈夫ですか？",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )

            # 4. Activity level sudden drop (>0.5 → <0.1 sustained 15min)
            if (
                occ.activity_level is not None
                and occ.activity_level < 0.1
                and occ.count > 0
                and occ.posture_duration_sec > 900
                and self._check_cooldown(f"percep_activity_drop_{zone_id}", now)
            ):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "しばらく動きがないようです。大丈夫ですか？",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )

            # 5. VLM anomaly detected — 3-stage escalation:
            #    (a) Initial alert when anomaly first observed (cooldown gated)
            #    (b) 5min persistence: escalate (speak + task)
            #    (c) 30min persistence: request VLM rescan (heavy) via MQTT (30min cooldown)
            if occ.scene_anomalies and occ.vlm_last_update > 0 and now - occ.vlm_last_update < 120:
                anomaly_text = "、".join(occ.scene_anomalies[:3])
                first_seen = occ.anomaly_first_seen or occ.vlm_last_update
                persist_sec = now - first_seen

                # (a) Initial alert
                if self._check_cooldown(f"percep_vlm_anomaly_{zone_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"カメラで異常を検知しました: {anomaly_text}。確認をお願いします。",
                                "zone": zone_id,
                                "tone": "alert",
                            },
                        }
                    )

                # (b) 5min escalation — speak + task if anomaly still present
                if persist_sec >= 300 and not occ.anomaly_escalated:
                    occ.anomaly_escalated = True
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"先ほどの異常({anomaly_text})が5分経過しても続いています。確認してください。",
                                "zone": zone_id,
                                "tone": "alert",
                            },
                        }
                    )
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"VLM異常持続: {zone_id}",
                                "description": f"{zone_id}で検知された異常 ({anomaly_text}) が5分以上継続しています。現地確認をお願いします。",
                                "urgency": 3,
                                "zone": zone_id,
                                "task_type": ["vlm_anomaly"],
                            },
                        }
                    )

                # (c) 30min persistence → re-request VLM heavy scan (30min cooldown)
                rescan_cooldown_ok = (now - occ.anomaly_rescan_requested) >= 1800
                if persist_sec >= 1800 and rescan_cooldown_ok and self.mqtt_publisher is not None:
                    try:
                        self.mqtt_publisher(
                            "hems/perception/vlm/request",
                            {"zone": zone_id, "reason": "anomaly_persisted_30min"},
                        )
                        occ.anomaly_rescan_requested = now
                    except Exception:
                        pass

        return actions

    def _evaluate_service_vip_rules(self, world_model, now: float) -> list[dict]:
        """B-2: Speak immediately on VIP service events (Gmail VIP sender, etc).

        Cooldown: 5 min per service to suppress storms.
        """
        actions: list[dict] = []
        ss = getattr(world_model, "services_state", None)
        if ss is None or not ss.events:
            return actions
        for ev in ss.events[-20:]:
            if ev.event_type != "service_vip_event":
                continue
            # Only fire for events less than 60s old (avoid speaking on replay)
            if ev.timestamp and now - ev.timestamp > 60:
                continue
            service = (ev.data or {}).get("service", "サービス")
            key = f"service_vip_{service}"
            if not self._check_cooldown_custom(key, now, 300):
                continue
            summary = ev.description or f"{service} で更新あり"
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"重要な通知です。{summary}",
                        "zone": "home",
                        "tone": "alert",
                    },
                }
            )
        return actions

    def _evaluate_device_health_rules(self, now: float) -> list[dict]:
        """B-5: Battery / LQI / staleness alerts for registered devices.

        Reads `self._device_cache` (populated by `refresh_devices`). Cooldowns:
        - battery_low: 7 days per device
        - link_quality_low: 24h per device
        - stale: 24h per device
        """
        actions: list[dict] = []
        if not self._device_cache:
            return actions

        WEEK_S = 7 * 86400
        DAY_S = 86400
        stale_threshold_s = DEVICE_STALE_HOURS * 3600

        for d in self._device_cache:
            if not d.get("is_enabled", True):
                continue
            device_id = d.get("device_id") or ""
            if not device_id:
                continue
            display = d.get("display_name") or device_id

            # Battery (≤10% by default)
            battery = d.get("battery_pct")
            if isinstance(battery, (int, float)) and battery <= DEVICE_BATTERY_LOW:
                if self._check_cooldown_custom(f"dev_battery_{device_id}", now, WEEK_S):
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"電池切れ間近: {display}",
                                "description": f"{display} の電池残量が{int(battery)}%です。早めの交換を。",
                                "urgency": 2,
                                "zone": d.get("zone") or "home",
                                "task_type": ["maintenance"],
                            },
                        }
                    )

            # Link quality (Z2M LQI < 50 means weak mesh signal)
            lqi = d.get("link_quality")
            if isinstance(lqi, (int, float)) and lqi < DEVICE_LQI_LOW and (d.get("vendor") == "zigbee"):
                if self._check_cooldown_custom(f"dev_lqi_{device_id}", now, DAY_S):
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"信号弱: {display}",
                                "description": f"{display} のZigbeeリンク品質が低下 (LQI={int(lqi)}). 中継器の追加か配置の見直しを検討してください。",
                                "urgency": 1,
                                "zone": d.get("zone") or "home",
                                "task_type": ["maintenance"],
                            },
                        }
                    )

            # Staleness (no updates for >24h)
            last_seen_iso = d.get("last_seen")
            last_seen_ts = parse_iso_ts(last_seen_iso)
            if last_seen_ts is not None and (now - last_seen_ts) > stale_threshold_s:
                if self._check_cooldown_custom(f"dev_stale_{device_id}", now, DAY_S):
                    hours_ago = int((now - last_seen_ts) / 3600)
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"反応なし: {display}",
                                "description": f"{display} は{hours_ago}時間応答していません。確認/再ペアリングしてください。",
                                "urgency": 2,
                                "zone": d.get("zone") or "home",
                                "task_type": ["maintenance"],
                            },
                        }
                    )

        return actions

    def _evaluate_zigbee_sensor_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate Zigbee binary_sensor and sensor rules."""
        actions = []
        hd = world_model.home_devices

        # --- Z1: Moisture emergency ---
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "moisture" and bs.state:
                if self._check_cooldown(f"zigbee_moisture_{eid}", now):
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

        # --- Z2: Door arrival/departure ---
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "door" and not bs.state and bs.previous_state:
                # door closed transition (was open, now closed)
                if now - bs.last_changed > 60:
                    continue  # too old
                if self._check_cooldown(f"zigbee_door_{eid}", now):
                    any_occupied = world_model.is_anyone_home()
                    if any_occupied:
                        # Arrival: turn on lights
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "おかえりなさい。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )
                        for d in self._get_devices(device_class="light"):
                            if not self._device_is_on(d):
                                actions.append(self._make_action(d["device_id"], "on"))
                    else:
                        # Departure: turn off lights + switches
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "いってらっしゃい。照明とスイッチを切りますね。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )
                        for d in self._get_devices(device_class="light"):
                            if self._device_is_on(d):
                                actions.append(self._make_action(d["device_id"], "off"))
                        for d in self._get_devices(device_class="switch"):
                            if self._device_is_on(d):
                                actions.append(self._make_action(d["device_id"], "off"))

        # --- Z3: Appliance finished (power drop to idle) ---
        for eid, s in hd.sensors.items():
            if s.device_class == "power" and s.previous_value > POWER_IDLE_WATTS and s.value <= POWER_IDLE_WATTS:
                if self._check_cooldown(f"zigbee_power_{eid}", now):
                    name = eid.split(".")[-1] if "." in eid else eid
                    name_lower = name.lower()
                    if any(w in name_lower for w in ("washing", "laundry", "washer", "洗濯")):
                        actions.append(
                            {
                                "tool": "create_task",
                                "args": {
                                    "title": "洗濯物を干す",
                                    "description": f"{name}の運転が完了しました。洗濯物を干してください。",
                                    "urgency": 2,
                                    "zone": "home",
                                    "task_type": ["laundry"],
                                },
                            }
                        )
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "洗濯が完了しました。洗濯物を干しましょう。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )
                    elif any(w in name_lower for w in ("kettle", "ケトル", "pot")):
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "お湯が沸きました。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )
                    else:
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"{name}の運転が完了しました。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )

        # --- Z4: CO2 high + all windows closed → ventilation suggestion ---
        co2_sensors = [s for s in hd.sensors.values() if s.device_class == "carbon_dioxide"]
        window_sensors = [bs for bs in hd.binary_sensors.values() if bs.device_class == "window"]
        for s in co2_sensors:
            if s.value > CO2_HIGH:
                all_closed = all(not ws.state for ws in window_sensors) if window_sensors else False
                if all_closed and self._check_cooldown(f"zigbee_co2_window_{s.entity_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"CO2が{int(s.value)}ppmです。窓を開けて換気しましょう。",
                                "zone": "home",
                                "tone": "caring",
                            },
                        }
                    )

        # --- Z5: PM2.5 high → purifier on ---
        pm25_sensors = [s for s in hd.sensors.values() if s.device_class == "pm25"]
        for s in pm25_sensors:
            if s.value > PM25_HIGH:
                if self._check_cooldown(f"zigbee_pm25_{s.entity_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"PM2.5が{int(s.value)}μg/m³です。空気清浄機をつけます。",
                                "zone": "home",
                                "tone": "caring",
                            },
                        }
                    )
                    for d in self._get_devices(device_class="switch"):
                        did = d.get("device_id", "").lower()
                        purpose = (d.get("purpose") or "").lower()
                        if any(w in did or w in purpose for w in ("purifier", "清浄", "air")):
                            actions.append(self._make_action(d["device_id"], "on"))

        # --- Z6: Vibration stopped (washing machine) ---
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "vibration" and not bs.state and bs.previous_state:
                name_lower = eid.lower()
                if any(w in name_lower for w in ("washing", "laundry", "washer", "洗濯")):
                    if self._check_cooldown(f"zigbee_vibration_{eid}", now):
                        actions.append(
                            {
                                "tool": "create_task",
                                "args": {
                                    "title": "洗濯物を干す",
                                    "description": "洗濯機の振動が停止しました。洗濯物を干してください。",
                                    "urgency": 2,
                                    "zone": "home",
                                    "task_type": ["laundry"],
                                },
                            }
                        )
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "洗濯機が止まりました。洗濯物を干しましょう。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )

        return actions

    def _evaluate_zigbee_critical_only(self, world_model, now: float) -> list[dict]:
        """In guest mode, only evaluate critical safety rules (water leak, extreme conditions)."""
        actions = []
        hd = world_model.home_devices
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "moisture" and bs.state:
                if self._check_cooldown(f"zigbee_moisture_{eid}", now):
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
        return actions

    def _evaluate_circadian_lighting(self, world_model, now: float) -> list[dict]:
        """Adjust light color temperature based on time of day (circadian rhythm)."""
        if not CIRCADIAN_ENABLED:
            return []
        if not self._check_cooldown("circadian_update", now):
            return []

        lights_on = [d for d in self._get_devices(device_class="light", capability="color_temp") if self._device_is_on(d)]
        if not lights_on:
            return []

        hour = datetime.now().hour + datetime.now().minute / 60.0
        target_mirek, target_brightness_pct = self._interpolate_circadian(hour)
        target_brightness = int(target_brightness_pct / 100 * 255)

        actions = []
        for d in lights_on:
            state = d.get("last_state") or {}
            ct = state.get("color_temp", 0)
            br = state.get("brightness", 0)
            if ct and abs(ct - target_mirek) < 20 and abs(br - target_brightness) < 15:
                continue
            actions.append(self._make_action(d["device_id"], "set_brightness", {"value": target_brightness}))
            actions.append(self._make_action(d["device_id"], "set_color_temp", {"value": target_mirek}))
        return actions

    @staticmethod
    def _interpolate_circadian(hour: float) -> tuple[int, int]:
        """Interpolate circadian curve for given fractional hour."""
        curve = CIRCADIAN_CURVE
        # Find surrounding points
        for i in range(len(curve) - 1):
            if curve[i][0] <= hour < curve[i + 1][0]:
                h0, m0, b0 = curve[i]
                h1, m1, b1 = curve[i + 1]
                t = (hour - h0) / (h1 - h0)
                return int(m0 + (m1 - m0) * t), int(b0 + (b1 - b0) * t)
        # After last point, use last value
        return curve[-1][1], curve[-1][2]

    def _evaluate_absence_lighting(self, world_model, now: float) -> list[dict]:
        """Randomly toggle lights during extended absence to simulate presence."""
        if not ABSENCE_LIGHTING_ENABLED:
            return []

        # Check every presence signal, not just the camera — otherwise the
        # absence-lighting prank can fire while the occupant is quietly at the PC.
        all_empty = bool(world_model.zones) and not world_model.is_anyone_home()
        if not all_empty:
            actions = []
            for did in list(self._absence_light_state.keys()):
                if self._absence_light_state[did]:
                    actions.append(self._make_action(did, "off"))
            self._absence_light_state.clear()
            return actions

        hour = datetime.now().hour
        if not (ABSENCE_LIGHTING_START_HOUR <= hour < ABSENCE_LIGHTING_END_HOUR):
            return []

        if not self._check_cooldown("absence_lighting", now):
            return []
        self._cooldowns["absence_lighting"] = (
            now - self.COOLDOWN_SECONDS + random.randint(ABSENCE_LIGHTING_INTERVAL // 2, ABSENCE_LIGHTING_INTERVAL)
        )

        all_lights = [d["device_id"] for d in self._get_devices(device_class="light")]
        if not all_lights:
            return []

        actions = []
        targets = random.sample(all_lights, min(2, len(all_lights)))
        for did in targets:
            currently_simulated = self._absence_light_state.get(did, False)
            new_state = not currently_simulated
            self._absence_light_state[did] = new_state
            if new_state:
                actions.append(self._make_action(did, "on"))
                actions.append(self._make_action(did, "set_brightness", {"value": random.randint(100, 200)}))
            else:
                actions.append(self._make_action(did, "off"))

        return actions

    def _evaluate_weather_rules(self, world_model, now: float) -> list[dict]:
        """Weather-based automation rules."""
        w = world_model.weather
        if w.last_update == 0 and w.last_alerts_update == 0:
            return []

        actions = []
        hd = world_model.home_devices

        # Severe weather alerts → speak + create_task (24h cooldown per alert title)
        severe_levels = {"warning", "severe", "extreme", "critical"}
        for alert in w.alerts:
            sev = (alert.severity or "").lower()
            if sev not in severe_levels or not alert.title:
                continue
            key = f"weather_alert_{alert.title}"
            if not self._check_cooldown_daily(key, now):
                continue
            area_part = f"（{alert.area}）" if alert.area else ""
            tone = "alert" if sev in ("extreme", "critical") else "caring"
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"気象警報: {alert.title}{area_part}。注意してください。",
                        "zone": "home",
                        "tone": tone,
                    },
                }
            )
            actions.append(
                {
                    "tool": "create_task",
                    "args": {
                        "title": f"気象警報: {alert.title}",
                        "description": (alert.description or alert.title)[:300],
                        "urgency": 4 if sev in ("extreme", "critical") else 3,
                        "zone": "home",
                        "task_type": ["weather_alert"],
                    },
                }
            )

        # Rain forecast + windows open → alert
        rain_soon = any(
            f.precipitation_probability > 60
            for f in w.forecast[:4]  # next ~4 hours
        )
        if rain_soon:
            open_windows = [bs for bs in hd.binary_sensors.values() if bs.device_class == "window" and bs.state]
            if open_windows and self._check_cooldown("weather_rain_window", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "雨の予報が出ています。窓を閉めてください。",
                            "zone": "home",
                            "tone": "caring",
                        },
                    }
                )

        # High temperature forecast → pre-cool advice
        hot_forecast = any(f.temperature > 33 for f in w.forecast[:6])
        if hot_forecast and self._check_cooldown_daily("weather_hot_forecast", now):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": "本日は猛暑の予報です。エアコンの早めの稼働をお勧めします。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

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
            if env.co2 is not None and env.co2 > CO2_CRITICAL and self._check_cooldown(f"critical_co2_{zone_id}", now):
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
                if env.temperature > TEMP_CRITICAL_HIGH and self._check_cooldown(f"critical_temp_high_{zone_id}", now):
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
                elif env.temperature < TEMP_CRITICAL_LOW and self._check_cooldown(f"critical_temp_low_{zone_id}", now):
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
            and bio.spo2.percent < SPO2_CRITICAL_LOW
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
            and bio.heart_rate.bpm > HR_CRITICAL_SLEEP
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

    def _evaluate_shopping_rules(self, wm, now: float) -> list[dict]:
        """Shopping list rules: recurring due reminders + departure notification."""
        actions = []
        shopping = wm.shopping_state

        # Recurring items due for purchase (24h cooldown per item)
        for item in shopping.due_items:
            key = f"shopping_due_{item.name}"
            if self._check_cooldown_daily(key, now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"「{item.name}」がそろそろ必要です。買い物リストを確認してください。",
                            "zone": "living_room",
                            "tone": "caring",
                        },
                    }
                )

        # Departure notification: occupancy drops to 0 with pending items.
        # Reconciled presence (camera + PIR + motion + PC + HR) prevents a
        # momentary camera dropout from nagging the user about shopping.
        if shopping.pending_count > 0:
            has_recent_zones = any(z.occupancy.last_update > now - 300 for z in wm.zones.values() if z.occupancy)
            all_empty = has_recent_zones and not wm.is_anyone_home()
            if all_empty and has_recent_zones:
                if self._check_cooldown("shopping_departure", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"外出検知。買い物リストに{shopping.pending_count}件のアイテムがあります。",
                                "zone": "living_room",
                                "tone": "caring",
                            },
                        }
                    )

        return actions
