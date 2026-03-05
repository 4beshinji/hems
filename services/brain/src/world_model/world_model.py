"""
WorldModel — maintains unified zone state from MQTT messages.
Forked from SOMS with HEMS personal topic support.
"""
import os
import re
import time
import logging
from typing import Optional
from .data_classes import (
    ZoneState, EnvironmentData, OccupancyData, Event,
    PCState, CPUData, MemoryData, GPUData, DiskData, DiskPartition, ProcessInfo,
    ServicesState, ServiceStatusData,
    KnowledgeState,
    GASState, CalendarEvent, FreeSlot, GoogleTask, GmailLabel, DriveFile, SheetData,
    HomeDevicesState, LightState, ClimateState, CoverState, BinarySensorState, HASensorState,
    WeatherState, WeatherForecast,
    BiometricState, HeartRateData, SleepData, ActivityData, StressData, FatigueData, SpO2Data,
    HRVData, BodyTemperatureData, RespiratoryRateData, ScreenTimeData,
    PhysicalSpace, DigitalSpace, UserState,
)
from .sensor_fusion import SensorFusion

logger = logging.getLogger(__name__)

# Prompt injection patterns to strip from MQTT-sourced text before LLM context
_INJECTION_RE = re.compile(
    r"\[SYSTEM|<\|system\|>|###\s*(System|Instruction|Override)|"
    r"Ignore\s+previous\s+instructions|Override\s+(all\s+)?(previous\s+)?instructions|"
    r"\[INST\]|<\|im_start\|>|<\|im_end\|>",
    re.IGNORECASE,
)


def _sanitize_text(text: str, max_len: int = 200) -> str:
    """Sanitize MQTT-sourced text before including it in LLM context.

    - Removes prompt-injection marker patterns
    - Collapses newlines (prevents multi-line injection)
    - Truncates to max_len
    """
    if not isinstance(text, str):
        return str(text)[:max_len]
    cleaned = _INJECTION_RE.sub("[FILTERED]", text)
    cleaned = " ".join(cleaned.splitlines()).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + "…"
    return cleaned

# Environment thresholds for event generation (configurable via env vars)
CO2_HIGH = int(os.getenv("HEMS_THRESHOLD_CO2_HIGH", "1000"))
CO2_CRITICAL = int(os.getenv("HEMS_THRESHOLD_CO2_CRITICAL", "1500"))
TEMP_HIGH = int(os.getenv("HEMS_THRESHOLD_TEMP_HIGH", "28"))
TEMP_LOW = int(os.getenv("HEMS_THRESHOLD_TEMP_LOW", "16"))
SEDENTARY_MINUTES = int(os.getenv("HEMS_THRESHOLD_SEDENTARY_MINUTES", "60"))

# PC thresholds (configurable via env vars)
PC_CPU_HIGH = int(os.getenv("HEMS_THRESHOLD_PC_CPU_HIGH", "90"))
PC_MEMORY_HIGH = int(os.getenv("HEMS_THRESHOLD_PC_MEMORY_HIGH", "90"))
PC_GPU_TEMP_HIGH = int(os.getenv("HEMS_THRESHOLD_PC_GPU_TEMP_HIGH", "85"))
PC_DISK_HIGH = int(os.getenv("HEMS_THRESHOLD_PC_DISK_HIGH", "90"))

# Biometric thresholds (configurable via env vars)
HR_HIGH = int(os.getenv("HEMS_THRESHOLD_HR_HIGH", "120"))
HR_LOW = int(os.getenv("HEMS_THRESHOLD_HR_LOW", "45"))
SPO2_LOW = int(os.getenv("HEMS_THRESHOLD_SPO2_LOW", "92"))
STRESS_HIGH = int(os.getenv("HEMS_THRESHOLD_STRESS_HIGH", "80"))

# Environment extended thresholds
HUMIDITY_HIGH = int(os.getenv("HEMS_THRESHOLD_HUMIDITY_HIGH", "70"))
HUMIDITY_LOW = int(os.getenv("HEMS_THRESHOLD_HUMIDITY_LOW", "30"))

# Extended biometric thresholds
HRV_LOW = int(os.getenv("HEMS_THRESHOLD_HRV_LOW", "20"))
BODY_TEMP_HIGH = float(os.getenv("HEMS_THRESHOLD_BODY_TEMP_HIGH", "37.5"))
RESPIRATORY_RATE_HIGH = int(os.getenv("HEMS_THRESHOLD_RESPIRATORY_RATE_HIGH", "25"))
SCREEN_TIME_ALERT_MINUTES = int(os.getenv("HEMS_THRESHOLD_SCREEN_TIME_MINUTES", "120"))

# Zigbee sensor thresholds
POWER_IDLE_WATTS = float(os.getenv("HEMS_THRESHOLD_POWER_IDLE_WATTS", "5"))
PM25_HIGH = float(os.getenv("HEMS_THRESHOLD_PM25_HIGH", "35"))


class WorldModel:
    # Default suppression duration (seconds) per alert type.
    # Slow-changing conditions get longer suppression to avoid duplicate tasks
    # while the physical environment slowly responds (e.g., AC cooling a room).
    SUPPRESSION_DEFAULTS: dict[str, float] = {
        "temp_high": 1800,    # 30 min — AC takes time to cool
        "temp_low": 1800,     # 30 min — heating takes time
        "co2_high": 600,      # 10 min — ventilation is faster
        "co2_critical": 600,  # 10 min
    }

    def __init__(self):
        # Tri-domain architecture
        self.physical = PhysicalSpace()
        self.digital = DigitalSpace()
        self.user = UserState()

        self._sensor_fusions: dict[str, SensorFusion] = {}
        self.event_writer = None  # Set by Brain if event_store is available

        # Alert suppression: {(zone_id, alert_type): expiry_timestamp}
        # Prevents repeated task creation for slow-changing conditions.
        self._suppressed_alerts: dict[tuple, float] = {}

        # Guest mode: temporarily pause non-critical automations
        self._guest_mode: bool = False
        self._guest_mode_expires: float = 0

    # --- Backward-compatible property accessors ---
    # These delegate to domain objects so existing code works unchanged.

    @property
    def zones(self) -> dict[str, ZoneState]:
        return self.physical.zones

    @zones.setter
    def zones(self, value: dict[str, ZoneState]):
        self.physical.zones = value

    @property
    def pc_state(self) -> PCState:
        return self.digital.pc_state

    @pc_state.setter
    def pc_state(self, value: PCState):
        self.digital.pc_state = value

    @property
    def services_state(self) -> ServicesState:
        return self.digital.services_state

    @services_state.setter
    def services_state(self, value: ServicesState):
        self.digital.services_state = value

    @property
    def knowledge_state(self) -> KnowledgeState:
        return self.digital.knowledge_state

    @knowledge_state.setter
    def knowledge_state(self, value: KnowledgeState):
        self.digital.knowledge_state = value

    @property
    def gas_state(self) -> GASState:
        return self.digital.gas_state

    @gas_state.setter
    def gas_state(self, value: GASState):
        self.digital.gas_state = value

    @property
    def home_devices(self) -> HomeDevicesState:
        return self.physical.home_devices

    @home_devices.setter
    def home_devices(self, value: HomeDevicesState):
        self.physical.home_devices = value

    @property
    def biometric_state(self) -> BiometricState:
        return self.user.biometrics

    @biometric_state.setter
    def biometric_state(self, value: BiometricState):
        self.user.biometrics = value

    # --- Guest mode ---

    @property
    def is_guest_mode(self) -> bool:
        if self._guest_mode and time.time() > self._guest_mode_expires:
            self._guest_mode = False
            logger.info("ゲストモード期限切れ — 自動解除")
        return self._guest_mode

    def set_guest_mode(self, enabled: bool, duration_hours: float = 4):
        self._guest_mode = enabled
        self._guest_mode_expires = time.time() + duration_hours * 3600 if enabled else 0
        logger.info("ゲストモード%s (期限: %.1f時間)", "ON" if enabled else "OFF", duration_hours if enabled else 0)

    # --- Weather ---

    @property
    def weather(self) -> WeatherState:
        return self.physical.weather

    def suppress_alert(self, zone_id: str, alert_type: str, duration: float = None):
        """Suppress an alert for a zone after a task has been created for it.

        Prevents the LLM from creating duplicate tasks while the physical
        environment slowly responds (e.g., AC cooling a room after task created).
        Auto-clears when sensor readings return to normal range.
        """
        if duration is None:
            duration = self.SUPPRESSION_DEFAULTS.get(alert_type, 1800)
        self._suppressed_alerts[(zone_id, alert_type)] = time.time() + duration
        logger.debug("Alert suppressed: zone=%s type=%s duration=%ds", zone_id, alert_type, duration)

    def _is_suppressed(self, zone_id: str, alert_type: str) -> bool:
        """Return True if this alert is currently suppressed."""
        key = (zone_id, alert_type)
        expiry = self._suppressed_alerts.get(key)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._suppressed_alerts[key]
            return False
        return True

    def clear_suppression(self, zone_id: str, alert_type: str):
        """Clear a suppression when the condition has resolved."""
        self._suppressed_alerts.pop((zone_id, alert_type), None)

    def get_zone(self, zone_id: str) -> Optional[ZoneState]:
        """Get state of a specific zone (returns None if zone not yet seen)."""
        return self.zones.get(zone_id)

    def get_all_zones(self) -> dict[str, ZoneState]:
        """Get all zones."""
        return self.zones

    def _get_zone(self, zone_id: str) -> ZoneState:
        """Get or create a zone by ID (internal use)."""
        if zone_id not in self.zones:
            self.zones[zone_id] = ZoneState(zone_id=zone_id)
        return self.zones[zone_id]

    def _get_fusion(self, key: str) -> SensorFusion:
        if key not in self._sensor_fusions:
            self._sensor_fusions[key] = SensorFusion()
        return self._sensor_fusions[key]

    def update_from_mqtt(self, topic: str, payload: dict):
        """Parse MQTT topic and update world state."""
        parts = topic.split("/")

        # office/{zone}/sensor/{device_id}/{channel}
        if len(parts) >= 5 and parts[0] == "office" and parts[2] == "sensor":
            zone_id = parts[1]
            channel = parts[4]
            value = payload.get(channel) or payload.get("value")
            if value is not None:
                self._update_sensor(zone_id, channel, float(value))

        # office/{zone}/camera/{camera_id}/status (occupancy)
        elif len(parts) >= 5 and parts[0] == "office" and parts[2] == "camera":
            zone_id = parts[1]
            count = payload.get("person_count", payload.get("count", 0))
            zone = self._get_zone(zone_id)
            zone.occupancy = OccupancyData(count=int(count), last_update=time.time())

        # office/{zone}/activity/{monitor_id} (activity/sedentary)
        elif len(parts) >= 4 and parts[0] == "office" and parts[2] == "activity":
            zone_id = parts[1]
            zone = self._get_zone(zone_id)
            activity = payload.get("activity_level", "")
            # Update activity fields on OccupancyData
            if isinstance(activity, float):
                zone.occupancy.activity_level = activity
            if "activity_class" in payload:
                zone.occupancy.activity_class = payload["activity_class"]
            if "posture" in payload:
                zone.occupancy.posture = payload["posture"]
            if "posture_duration_sec" in payload:
                zone.occupancy.posture_duration_sec = payload["posture_duration_sec"]
            if "posture_status" in payload:
                zone.occupancy.posture_status = payload["posture_status"]
            # Legacy: sedentary string value
            if activity == "sedentary":
                duration = payload.get("duration_minutes", 0)
                if duration >= SEDENTARY_MINUTES:
                    zone.add_event(Event(
                        event_type="sedentary_alert",
                        description=f"長時間着座検知: {duration}分",
                        severity=1,
                        zone=zone_id,
                        data={"duration_minutes": duration},
                    ))

        # office/{zone}/task_report/{task_id}
        elif "task_report" in topic:
            zone_id = parts[1] if len(parts) >= 2 else "unknown"
            zone = self._get_zone(zone_id)
            safe_title = _sanitize_text(payload.get("title", ""), 100)
            safe_status = _sanitize_text(payload.get("report_status", ""), 30)
            zone.add_event(Event(
                event_type="task_report",
                description=f"タスク報告: {safe_title} ({safe_status})",
                severity=1 if payload.get("report_status") in ("needs_followup", "cannot_resolve") else 0,
                zone=zone_id,
                data=payload,
            ))

        # hems/pc/* topics (OpenClaw bridge)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "pc":
            self._update_pc_state(parts[2:], payload)

        # hems/services/{name}/status (Service Monitor)
        elif parts[0] == "hems" and len(parts) >= 4 and parts[1] == "services":
            self._update_service_state(parts[2], parts[3], payload)

        # hems/home/* topics (HA bridge)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "home":
            self._update_home_device(parts[2:], payload)

        # hems/gas/* topics (GAS bridge)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "gas":
            self._update_gas_state(parts[2:], payload)

        # hems/personal/* topics (Phase 2 — data-bridge)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "personal":
            self._update_personal(parts[2:], payload)

    def _update_sensor(self, zone_id: str, channel: str, value: float):
        zone = self._get_zone(zone_id)
        fusion_key = f"{zone_id}/{channel}"
        fusion = self._get_fusion(fusion_key)
        fusion.add_reading(value)
        fused = fusion.get_value()

        if fused is None:
            return

        env = zone.environment
        prev = getattr(env, channel, None) if hasattr(env, channel) else None

        if channel == "temperature":
            env.temperature = round(fused, 1)
        elif channel == "humidity":
            env.humidity = round(fused, 1)
        elif channel == "co2":
            env.co2 = round(fused, 0)
        elif channel == "pressure":
            env.pressure = round(fused, 1)
        elif channel == "light":
            env.light = round(fused, 1)
        elif channel == "voc":
            env.voc = round(fused, 1)

        env.last_update = time.time()

        # Generate events from threshold crossings
        self._check_thresholds(zone, channel, fused, prev)

    def _check_thresholds(self, zone: ZoneState, channel: str, value: float, prev: float | None):
        zid = zone.zone_id
        if channel == "co2":
            # Auto-clear suppression when CO2 returns to normal
            if value <= CO2_HIGH:
                self.clear_suppression(zid, "co2_high")
                self.clear_suppression(zid, "co2_critical")

            if value > CO2_CRITICAL and (prev is None or prev <= CO2_CRITICAL):
                if not self._is_suppressed(zid, "co2_critical"):
                    zone.add_event(Event(
                        event_type="co2_critical",
                        description=f"CO2危険レベル: {int(value)}ppm",
                        severity=2,
                        zone=zid,
                        data={"co2": value},
                    ))
            elif value > CO2_HIGH and (prev is None or prev <= CO2_HIGH):
                if not self._is_suppressed(zid, "co2_high"):
                    zone.add_event(Event(
                        event_type="co2_high",
                        description=f"CO2上昇: {int(value)}ppm",
                        severity=1,
                        zone=zid,
                        data={"co2": value},
                    ))

        elif channel == "temperature":
            # Auto-clear suppression when temperature returns to normal range
            if TEMP_LOW <= value <= TEMP_HIGH:
                self.clear_suppression(zid, "temp_high")
                self.clear_suppression(zid, "temp_low")

            if value > TEMP_HIGH and (prev is None or prev <= TEMP_HIGH):
                if not self._is_suppressed(zid, "temp_high"):
                    zone.add_event(Event(
                        event_type="temp_high",
                        description=f"室温上昇: {value:.1f}度",
                        severity=1,
                        zone=zid,
                        data={"temperature": value},
                    ))
            elif value < TEMP_LOW and (prev is None or prev >= TEMP_LOW):
                if not self._is_suppressed(zid, "temp_low"):
                    zone.add_event(Event(
                        event_type="temp_low",
                        description=f"室温低下: {value:.1f}度",
                        severity=1,
                        zone=zid,
                        data={"temperature": value},
                    ))

    def _update_pc_state(self, path_parts: list[str], payload: dict):
        """Handle hems/pc/* topics from OpenClaw bridge."""
        if not path_parts:
            return

        category = path_parts[0]
        pc = self.pc_state

        if category == "metrics" and len(path_parts) >= 2:
            metric = path_parts[1]
            now = time.time()
            if metric == "cpu":
                prev_usage = pc.cpu.usage_percent
                pc.cpu = CPUData(
                    usage_percent=payload.get("usage_percent", 0),
                    core_count=payload.get("core_count", 0),
                    freq_mhz=payload.get("freq_mhz", 0),
                    temp_c=payload.get("temp_c", 0),
                    last_update=now,
                )
                self._check_pc_thresholds("cpu", pc.cpu.usage_percent, prev_usage)
            elif metric == "memory":
                prev_pct = pc.memory.percent
                pc.memory = MemoryData(
                    used_gb=payload.get("used_gb", 0),
                    total_gb=payload.get("total_gb", 0),
                    percent=payload.get("percent", 0),
                    last_update=now,
                )
                self._check_pc_thresholds("memory", pc.memory.percent, prev_pct)
            elif metric == "gpu":
                prev_temp = pc.gpu.temp_c
                pc.gpu = GPUData(
                    usage_percent=payload.get("usage_percent", 0),
                    vram_used_gb=payload.get("vram_used_gb", 0),
                    vram_total_gb=payload.get("vram_total_gb", 0),
                    temp_c=payload.get("temp_c", 0),
                    last_update=now,
                )
                self._check_pc_thresholds("gpu_temp", pc.gpu.temp_c, prev_temp)
            elif metric == "disk":
                partitions = [
                    DiskPartition(
                        mount=p.get("mount", ""),
                        used_gb=p.get("used_gb", 0),
                        total_gb=p.get("total_gb", 0),
                        percent=p.get("percent", 0),
                    )
                    for p in payload.get("partitions", [])
                ]
                pc.disk = DiskData(partitions=partitions, last_update=now)
                for p in partitions:
                    if p.percent > PC_DISK_HIGH:
                        pc.add_event(Event(
                            event_type="pc_disk_high",
                            description=f"ディスク残量警告: {p.mount} ({p.percent:.0f}%使用)",
                            severity=1,
                            data={"mount": p.mount, "percent": p.percent},
                        ))
            elif metric == "temperature":
                if "cpu_temp_c" in payload:
                    pc.cpu.temp_c = payload["cpu_temp_c"]
                if "gpu_temp_c" in payload:
                    pc.gpu.temp_c = payload["gpu_temp_c"]

        elif category == "processes" and len(path_parts) >= 2 and path_parts[1] == "top":
            pc.top_processes = [
                ProcessInfo(
                    pid=p.get("pid", 0),
                    name=p.get("name", ""),
                    cpu_percent=p.get("cpu_percent", 0),
                    mem_mb=p.get("mem_mb", 0),
                )
                for p in payload.get("processes", [])
            ]

        elif category == "bridge" and len(path_parts) >= 2 and path_parts[1] == "status":
            pc.bridge_connected = payload.get("connected", False)

        elif category == "events":
            # Threshold events from bridge (cpu_high, memory_high, gpu_hot, disk_low)
            event_type = path_parts[1] if len(path_parts) >= 2 else "unknown"
            pc.add_event(Event(
                event_type=f"pc_{event_type}",
                description=f"PC閾値イベント: {event_type}",
                severity=1 if "hot" not in event_type else 2,
                data=payload,
            ))

        # Update screen time tracking when PC metrics are received
        if pc.bridge_connected and pc.cpu.last_update > 0:
            self._update_screen_time(pc.cpu.last_update)

    def _update_screen_time(self, now: float):
        """Track daily screen time based on PC activity."""
        st = self.user.screen_time
        from datetime import datetime
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

        # Reset daily counter if new day
        if st.session_start_ts < today_start:
            st.total_minutes = 0
            st.session_start_ts = now
        elif st.last_update > 0:
            # Increment by elapsed time since last update (cap at 5 min gap)
            elapsed = now - st.last_update
            if 0 < elapsed < 300:
                st.total_minutes += int(elapsed / 60)
        else:
            st.session_start_ts = now

        st.last_update = now

    def _check_pc_thresholds(self, metric: str, value: float, prev: float):
        """Generate events from PC metric threshold crossings."""
        pc = self.pc_state
        if metric == "cpu" and value > PC_CPU_HIGH and prev <= PC_CPU_HIGH:
            pc.add_event(Event(
                event_type="pc_cpu_high",
                description=f"PC CPU使用率高: {value:.0f}%",
                severity=1,
                data={"usage_percent": value},
            ))
        elif metric == "memory" and value > PC_MEMORY_HIGH and prev <= PC_MEMORY_HIGH:
            pc.add_event(Event(
                event_type="pc_memory_high",
                description=f"PCメモリ使用率高: {value:.0f}%",
                severity=1,
                data={"percent": value},
            ))
        elif metric == "gpu_temp" and value > PC_GPU_TEMP_HIGH and prev <= PC_GPU_TEMP_HIGH:
            pc.add_event(Event(
                event_type="pc_gpu_hot",
                description=f"GPU温度警告: {value:.0f}°C",
                severity=2,
                data={"temp_c": value},
            ))

    def _update_service_state(self, service_name: str, msg_type: str, payload: dict):
        """Handle hems/services/{name}/status and hems/services/{name}/event topics."""
        ss = self.services_state

        if msg_type == "status":
            prev = ss.services.get(service_name)
            prev_count = prev.unread_count if prev else 0

            ssd = ServiceStatusData(
                name=_sanitize_text(payload.get("name", service_name), 50),
                available=bool(payload.get("available", True)),
                unread_count=int(payload.get("unread_count", 0)),
                summary=_sanitize_text(payload.get("summary", "")),
                details=payload.get("details", {}),
                last_check=payload.get("last_check", time.time()),
                error=_sanitize_text(payload.get("error", "") or "", 100) or None,
            )
            ss.services[service_name] = ssd

            # Generate event on unread increase
            if ssd.unread_count > prev_count:
                ss.add_event(Event(
                    event_type="service_unread_increase",
                    description=ssd.summary,
                    severity=0,
                    data={"service": service_name, "prev": prev_count, "new": ssd.unread_count},
                ))

        elif msg_type == "event":
            ss.add_event(Event(
                event_type=f"service_{payload.get('type', 'unknown')}",
                description=_sanitize_text(payload.get("summary", f"{service_name} event")),
                severity=0,
                data=payload,
            ))

    def _update_gas_state(self, path_parts: list[str], payload: dict):
        """Handle hems/gas/* topics from GAS bridge."""
        if not path_parts:
            return

        gs = self.gas_state
        category = path_parts[0]

        if category == "calendar" and len(path_parts) >= 2:
            sub = path_parts[1]
            if sub == "upcoming":
                events = []
                for ev in payload.get("events", []):
                    start_ts = self._parse_iso_ts(ev.get("start", ""))
                    end_ts = self._parse_iso_ts(ev.get("end", ""))
                    events.append(CalendarEvent(
                        id=ev.get("id", ""),
                        title=ev.get("title", ""),
                        start=ev.get("start", ""),
                        end=ev.get("end", ""),
                        location=ev.get("location", ""),
                        calendar_name=ev.get("calendarName", ""),
                        is_all_day=ev.get("isAllDay", False),
                        description=ev.get("description", ""),
                        start_ts=start_ts,
                        end_ts=end_ts,
                    ))
                gs.calendar_events = events
                gs.last_calendar_update = time.time()
                gs.bridge_connected = True

            elif sub == "free_slots":
                gs.free_slots = [
                    FreeSlot(
                        start=s.get("start", ""),
                        end=s.get("end", ""),
                        duration_minutes=s.get("duration_minutes", 0),
                    )
                    for s in payload.get("slots", [])
                ]

        elif category == "tasks" and len(path_parts) >= 2:
            sub = path_parts[1]
            tasks = []
            for tl in payload.get("taskLists", []):
                list_name = tl.get("title", "")
                for t in tl.get("tasks", []):
                    tasks.append(GoogleTask(
                        id=t.get("id", ""),
                        title=t.get("title", ""),
                        notes=t.get("notes", ""),
                        due=t.get("due", ""),
                        status=t.get("status", ""),
                        list_name=list_name,
                        is_overdue=t.get("is_overdue", False),
                    ))
            if sub == "all":
                gs.tasks = tasks
                gs.last_tasks_update = time.time()
            elif sub == "due_today":
                # Overwrite tasks list with due_today data (richer with is_overdue)
                gs.tasks = tasks
                gs.last_tasks_update = time.time()
            gs.bridge_connected = True

        elif category == "gmail" and len(path_parts) >= 2:
            sub = path_parts[1]
            if sub == "summary":
                gs.gmail_labels = {}
                for name, data in payload.get("labels", {}).items():
                    gs.gmail_labels[name] = GmailLabel(
                        name=name,
                        unread=data.get("unread", 0),
                        total=data.get("total", 0) or 0,
                    )
                gs.last_gmail_update = time.time()
                gs.bridge_connected = True
            elif sub == "recent":
                gs.gmail_recent = payload.get("threads", [])

        elif category == "sheets" and len(path_parts) >= 2:
            sheet_name = path_parts[1]
            gs.sheets[sheet_name] = SheetData(
                name=sheet_name,
                values=payload.get("values", []),
                headers=payload.get("headers", []),
                last_update=time.time(),
            )
            gs.bridge_connected = True

        elif category == "drive" and len(path_parts) >= 2:
            sub = path_parts[1]
            if sub == "recent":
                gs.drive_recent = [
                    DriveFile(
                        name=f.get("name", ""),
                        mime_type=f.get("mimeType", ""),
                        modified_time=f.get("modifiedTime", ""),
                        url=f.get("url", ""),
                    )
                    for f in payload.get("files", [])
                ]
                gs.bridge_connected = True

        elif category == "bridge" and len(path_parts) >= 2:
            if path_parts[1] == "status":
                gs.bridge_connected = payload.get("connected", False)

    @staticmethod
    def _parse_iso_ts(iso_str: str) -> float:
        """Parse ISO 8601 string to UNIX timestamp. Returns 0 on failure."""
        if not iso_str:
            return 0
        try:
            from datetime import datetime, timezone
            # Handle Z suffix and various formats
            s = iso_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt.timestamp()
        except (ValueError, TypeError):
            return 0

    def _update_personal(self, path_parts: list[str], payload: dict):
        """Handle hems/personal/* topics."""
        if not path_parts:
            return
        category = path_parts[0]

        # hems/personal/notes/* (Obsidian bridge)
        if category == "notes" and len(path_parts) >= 2:
            self._update_knowledge_state(path_parts[1], payload)

        # hems/personal/biometrics/{provider}/{metric}
        elif category == "biometrics" and len(path_parts) >= 2:
            self._update_biometric_state(path_parts[1:], payload)

    def _update_biometric_state(self, path_parts: list[str], payload: dict):
        """Handle hems/personal/biometrics/* topics from biometric bridge."""
        if not path_parts:
            return

        bio = self.biometric_state
        now = time.time()

        # hems/personal/biometrics/bridge/status
        if path_parts[0] == "bridge" and len(path_parts) >= 2 and path_parts[1] == "status":
            bio.bridge_connected = payload.get("connected", False)
            bio.provider = payload.get("provider", "")
            return

        # hems/personal/biometrics/{provider}/{metric}
        if len(path_parts) < 2:
            return

        metric = path_parts[1]

        if metric == "heart_rate":
            bpm = payload.get("bpm")
            if bpm is not None:
                prev_bpm = bio.heart_rate.bpm
                bio.heart_rate.bpm = int(bpm)
                bio.heart_rate.zone = HeartRateData.classify_zone(int(bpm))
                bio.heart_rate.last_update = now
                if "resting_bpm" in payload:
                    bio.heart_rate.resting_bpm = int(payload["resting_bpm"])
                bio.bridge_connected = True
                self._check_biometric_thresholds("heart_rate", float(bpm), float(prev_bpm) if prev_bpm else None)

        elif metric == "spo2":
            pct = payload.get("percent")
            if pct is not None:
                prev_pct = bio.spo2.percent
                bio.spo2.percent = int(pct)
                bio.spo2.last_update = now
                bio.bridge_connected = True
                self._check_biometric_thresholds("spo2", float(pct), float(prev_pct) if prev_pct else None)

        elif metric == "sleep":
            bio.sleep.stage = payload.get("stage", bio.sleep.stage)
            if "duration_minutes" in payload:
                bio.sleep.duration_minutes = int(payload["duration_minutes"])
            if "deep_minutes" in payload:
                bio.sleep.deep_minutes = int(payload["deep_minutes"])
            if "rem_minutes" in payload:
                bio.sleep.rem_minutes = int(payload["rem_minutes"])
            if "light_minutes" in payload:
                bio.sleep.light_minutes = int(payload["light_minutes"])
            if "quality_score" in payload:
                bio.sleep.quality_score = int(payload["quality_score"])
            if "sleep_start_ts" in payload:
                bio.sleep.sleep_start_ts = float(payload["sleep_start_ts"])
            if "sleep_end_ts" in payload:
                bio.sleep.sleep_end_ts = float(payload["sleep_end_ts"])
            bio.sleep.last_update = now
            bio.bridge_connected = True

        elif metric == "activity":
            if "steps" in payload:
                bio.activity.steps = int(payload["steps"])
            if "steps_goal" in payload:
                bio.activity.steps_goal = int(payload["steps_goal"])
            if "calories" in payload:
                bio.activity.calories = int(payload["calories"])
            if "active_minutes" in payload:
                bio.activity.active_minutes = int(payload["active_minutes"])
            if "level" in payload:
                bio.activity.level = payload["level"]
            bio.activity.last_update = now
            bio.bridge_connected = True

        elif metric == "stress":
            level = payload.get("level")
            if level is not None:
                prev_level = bio.stress.level
                bio.stress.level = int(level)
                bio.stress.category = StressData.classify_category(int(level))
                bio.stress.last_update = now
                bio.bridge_connected = True
                self._check_biometric_thresholds("stress", float(level), float(prev_level) if prev_level else None)

        elif metric == "fatigue":
            if "score" in payload:
                bio.fatigue.score = int(payload["score"])
            if "factors" in payload:
                bio.fatigue.factors = payload["factors"]
            bio.fatigue.last_update = now
            bio.bridge_connected = True

        elif metric == "hrv":
            rmssd = payload.get("rmssd_ms")
            if rmssd is not None:
                prev_rmssd = bio.hrv.rmssd_ms
                bio.hrv.rmssd_ms = int(rmssd)
                bio.hrv.last_update = now
                bio.bridge_connected = True
                if int(rmssd) < HRV_LOW and (prev_rmssd is None or prev_rmssd >= HRV_LOW):
                    bio.add_event(Event(
                        event_type="hrv_low",
                        description=f"HRV低下: {int(rmssd)}ms",
                        severity=1,
                        data={"rmssd_ms": int(rmssd)},
                    ))

        elif metric == "body_temperature":
            celsius = payload.get("celsius")
            if celsius is not None:
                prev_temp = bio.body_temperature.celsius
                bio.body_temperature.celsius = float(celsius)
                bio.body_temperature.last_update = now
                bio.bridge_connected = True
                if float(celsius) > BODY_TEMP_HIGH and (prev_temp is None or prev_temp <= BODY_TEMP_HIGH):
                    bio.add_event(Event(
                        event_type="body_temp_high",
                        description=f"体温上昇: {float(celsius):.1f}°C",
                        severity=1,
                        data={"celsius": float(celsius)},
                    ))

        elif metric == "respiratory_rate":
            rate = payload.get("breaths_per_minute")
            if rate is not None:
                prev_rate = bio.respiratory_rate.breaths_per_minute
                bio.respiratory_rate.breaths_per_minute = int(rate)
                bio.respiratory_rate.last_update = now
                bio.bridge_connected = True
                if int(rate) > RESPIRATORY_RATE_HIGH and (prev_rate is None or prev_rate <= RESPIRATORY_RATE_HIGH):
                    bio.add_event(Event(
                        event_type="respiratory_rate_high",
                        description=f"呼吸数上昇: {int(rate)}回/分",
                        severity=1,
                        data={"breaths_per_minute": int(rate)},
                    ))

        elif metric == "steps":
            # Alternative topic: hems/personal/biometrics/{provider}/steps
            if "count" in payload:
                bio.activity.steps = int(payload["count"])
            if "daily_goal" in payload:
                bio.activity.steps_goal = int(payload["daily_goal"])
            bio.activity.last_update = now
            bio.bridge_connected = True

    def _check_biometric_thresholds(self, metric: str, value: float, prev: float | None):
        """Generate events from biometric threshold crossings."""
        bio = self.biometric_state

        if metric == "heart_rate":
            if value > HR_HIGH and (prev is None or prev <= HR_HIGH):
                bio.add_event(Event(
                    event_type="hr_high",
                    description=f"心拍数上昇: {int(value)}bpm",
                    severity=1,
                    data={"bpm": value},
                ))
            elif value < HR_LOW and (prev is None or prev >= HR_LOW):
                bio.add_event(Event(
                    event_type="hr_low",
                    description=f"心拍数低下: {int(value)}bpm",
                    severity=1,
                    data={"bpm": value},
                ))

        elif metric == "spo2":
            if value < SPO2_LOW and (prev is None or prev >= SPO2_LOW):
                bio.add_event(Event(
                    event_type="spo2_low",
                    description=f"SpO2低下: {int(value)}%",
                    severity=2,
                    data={"percent": value},
                ))

        elif metric == "stress":
            if value > STRESS_HIGH and (prev is None or prev <= STRESS_HIGH):
                bio.add_event(Event(
                    event_type="stress_high",
                    description=f"ストレス高: {int(value)}",
                    severity=1,
                    data={"level": value},
                ))

    def _update_home_device(self, path_parts: list[str], payload: dict):
        """Handle hems/home/{zone}/{domain}/{entity_id}/state topics from HA bridge."""
        # hems/home/bridge/status
        if len(path_parts) >= 2 and path_parts[0] == "bridge" and path_parts[1] == "status":
            self.home_devices.bridge_connected = payload.get("connected", False)
            return

        # hems/home/{zone}/{domain}/{entity_id}/state
        if len(path_parts) < 3:
            return

        domain = path_parts[1] if len(path_parts) >= 2 else ""
        entity_id = path_parts[2] if len(path_parts) >= 3 else ""
        now = time.time()
        hd = self.home_devices
        hd.bridge_connected = True

        if domain == "light":
            hd.lights[entity_id] = LightState(
                entity_id=entity_id,
                on=payload.get("on", payload.get("state") == "on"),
                brightness=payload.get("brightness", 0),
                color_temp=payload.get("color_temp", 0),
                last_update=now,
            )
        elif domain == "climate":
            hd.climates[entity_id] = ClimateState(
                entity_id=entity_id,
                mode=payload.get("hvac_mode", payload.get("state", "off")),
                target_temp=payload.get("temperature", 0) or 0,
                current_temp=payload.get("current_temperature", 0) or 0,
                fan_mode=payload.get("fan_mode", "auto"),
                last_update=now,
            )
        elif domain == "cover":
            hd.covers[entity_id] = CoverState(
                entity_id=entity_id,
                position=payload.get("current_position", 0),
                is_open=payload.get("is_open", payload.get("state") == "open"),
                last_update=now,
            )
        elif domain == "switch":
            hd.switches[entity_id] = payload.get("on", payload.get("state") == "on")
        elif domain == "binary_sensor":
            raw_state = payload.get("state", "off")
            new_state = raw_state in ("on", "detected", "open", "wet")
            existing = hd.binary_sensors.get(entity_id)
            prev_state = existing.state if existing else False
            changed = existing is None or prev_state != new_state
            hd.binary_sensors[entity_id] = BinarySensorState(
                entity_id=entity_id,
                state=new_state,
                device_class=payload.get("device_class", existing.device_class if existing else ""),
                last_update=now,
                last_changed=now if changed else (existing.last_changed if existing else now),
                previous_state=prev_state,
            )
            if changed and existing is not None:
                self._handle_binary_sensor_event(hd, entity_id, new_state, prev_state,
                                                  hd.binary_sensors[entity_id].device_class)
        elif domain == "weather":
            w = self.physical.weather
            w.condition = payload.get("state", payload.get("condition", w.condition))
            if "temperature" in payload:
                w.temperature = float(payload["temperature"])
            if "humidity" in payload:
                w.humidity = float(payload["humidity"])
            if "wind_speed" in payload:
                w.wind_speed = float(payload["wind_speed"])
            forecasts = payload.get("forecast", [])
            if forecasts:
                w.forecast = [
                    WeatherForecast(
                        datetime=f.get("datetime", ""),
                        condition=f.get("condition", ""),
                        temperature=float(f.get("temperature", 0)),
                        precipitation_probability=int(f.get("precipitation_probability", 0)),
                        wind_speed=float(f.get("wind_speed", 0)),
                    )
                    for f in forecasts[:12]
                ]
            w.last_update = now
            return
        elif domain == "sensor":
            try:
                raw_val = payload.get("state", payload.get("value", 0))
                value = float(raw_val) if raw_val not in (None, "unknown", "unavailable", "") else 0
            except (ValueError, TypeError):
                value = 0
            existing = hd.sensors.get(entity_id)
            prev_value = existing.value if existing else 0
            device_class = payload.get("device_class", existing.device_class if existing else "")
            hd.sensors[entity_id] = HASensorState(
                entity_id=entity_id,
                value=value,
                unit=payload.get("unit_of_measurement", payload.get("unit", existing.unit if existing else "")),
                device_class=device_class,
                last_update=now,
                previous_value=prev_value,
            )
            if device_class == "power":
                self._check_power_thresholds(hd, entity_id, value, prev_value)

    def _handle_binary_sensor_event(self, hd, entity_id: str, new_state: bool,
                                     prev_state: bool, device_class: str):
        """Generate events for binary sensor state transitions."""
        if device_class in ("door", "window"):
            event_type = f"{device_class}_{'opened' if new_state else 'closed'}"
            desc = f"{'開' if new_state else '閉'}きました ({entity_id})"
            hd.add_event(Event(
                event_type=event_type,
                description=desc,
                severity=0,
                data={"entity_id": entity_id, "device_class": device_class, "state": new_state},
            ))
        elif device_class == "moisture" and new_state:
            hd.add_event(Event(
                event_type="moisture_detected",
                description=f"水漏れ検知 ({entity_id})",
                severity=2,
                data={"entity_id": entity_id},
            ))
        elif device_class == "vibration" and not new_state:
            hd.add_event(Event(
                event_type="vibration_stopped",
                description=f"振動停止 ({entity_id})",
                severity=0,
                data={"entity_id": entity_id},
            ))

    def _check_power_thresholds(self, hd, entity_id: str, value: float, prev_value: float):
        """Generate event when power drops to idle level."""
        if prev_value > POWER_IDLE_WATTS and value <= POWER_IDLE_WATTS:
            hd.add_event(Event(
                event_type="power_drop_idle",
                description=f"電力がアイドルに低下 ({entity_id}: {prev_value:.1f}W → {value:.1f}W)",
                severity=0,
                data={"entity_id": entity_id, "value": value, "previous_value": prev_value},
            ))

    def _update_knowledge_state(self, msg_type: str, payload: dict):
        """Handle hems/personal/notes/stats and hems/personal/notes/changed."""
        ks = self.knowledge_state

        if msg_type == "stats":
            ks.total_notes = payload.get("total_notes", 0)
            ks.indexed = payload.get("indexed", 0)
            ks.bridge_connected = True

        elif msg_type == "changed":
            ks.bridge_connected = True
            change = {
                "path": _sanitize_text(payload.get("path", ""), 150),
                "title": _sanitize_text(payload.get("title", ""), 100),
                "action": _sanitize_text(payload.get("action", ""), 30),
            }
            ks.add_recent_change(change)
            ks.add_event(Event(
                event_type="note_changed",
                description=f"ノート変更: {change['title']} ({change['action']})",
                severity=0,
                data=payload,
            ))

    def get_llm_context(self) -> str:
        """Build text context for LLM from current world state (tri-domain)."""
        sections = []

        physical = self._get_physical_context()
        if physical:
            sections.append("## 現実空間\n" + physical)

        digital = self._get_digital_context()
        if digital:
            sections.append("## 電子空間\n" + digital)

        user = self._get_user_context()
        if user:
            sections.append("## ユーザー状態\n" + user)

        return "\n\n".join(sections)

    def _get_physical_context(self) -> str:
        """Build physical space context (zones + smart home)."""
        lines = []

        # Zone data
        for zone_id, zone in self.zones.items():
            env = zone.environment
            parts = [f"### {zone_id}"]

            if env.temperature is not None:
                temp_str = f"  温度: {env.temperature}度 ({env.thermal_comfort})"
                if env.temperature > TEMP_HIGH and self._is_suppressed(zone_id, "temp_high"):
                    temp_str += " (対応中)"
                elif env.temperature < TEMP_LOW and self._is_suppressed(zone_id, "temp_low"):
                    temp_str += " (対応中)"
                parts.append(temp_str)
            if env.humidity is not None:
                parts.append(f"  湿度: {env.humidity}%")
            if env.co2 is not None:
                co2_str = f"  CO2: {int(env.co2)}ppm"
                if env.is_stuffy and (
                    self._is_suppressed(zone_id, "co2_high") or
                    self._is_suppressed(zone_id, "co2_critical")
                ):
                    co2_str += " (対応中)"
                elif env.is_stuffy:
                    co2_str += " (換気推奨)"
                parts.append(co2_str)
            if zone.occupancy and zone.occupancy.count > 0:
                parts.append(f"  在室: {zone.occupancy.count}人")
                if zone.occupancy.activity_class != "unknown":
                    parts.append(f"  活動: {zone.occupancy.activity_class} (レベル{zone.occupancy.activity_level:.1f})")
                if zone.occupancy.posture != "unknown":
                    duration_min = int(zone.occupancy.posture_duration_sec / 60)
                    parts.append(f"  姿勢: {zone.occupancy.posture} ({duration_min}分)")

            lines.append("\n".join(parts))

        # Home devices (HA integration)
        hd = self.home_devices
        if hd.bridge_connected:
            home_parts = ["### スマートホーム"]
            lights_on = [l for l in hd.lights.values() if l.on]
            lights_off = [l for l in hd.lights.values() if not l.on]
            if lights_on:
                for l in lights_on:
                    name = l.entity_id.split(".")[-1] if "." in l.entity_id else l.entity_id
                    pct = int(l.brightness / 255 * 100) if l.brightness else 100
                    home_parts.append(f"  照明: {name} ON({pct}%)")
            if lights_off:
                names = ", ".join(
                    l.entity_id.split(".")[-1] if "." in l.entity_id else l.entity_id
                    for l in lights_off
                )
                home_parts.append(f"  照明: {names} OFF")

            for c in hd.climates.values():
                name = c.entity_id.split(".")[-1] if "." in c.entity_id else c.entity_id
                mode_names = {"off": "停止", "cool": "冷房", "heat": "暖房",
                              "dry": "除湿", "fan_only": "送風", "auto": "自動"}
                mode_ja = mode_names.get(c.mode, c.mode)
                temp_str = f"{c.target_temp:.0f}°C" if c.target_temp else ""
                curr_str = f" (室温{c.current_temp:.1f}°C)" if c.current_temp else ""
                home_parts.append(f"  エアコン: {name} {mode_ja}{temp_str}{curr_str}")

            for cv in hd.covers.values():
                name = cv.entity_id.split(".")[-1] if "." in cv.entity_id else cv.entity_id
                status = "全開" if cv.position >= 95 else "閉" if cv.position <= 5 else f"{cv.position}%"
                home_parts.append(f"  カーテン: {name} {status}")

            if hd.switches:
                on_switches = [k.split(".")[-1] if "." in k else k
                               for k, v in hd.switches.items() if v]
                off_switches = [k.split(".")[-1] if "." in k else k
                                for k, v in hd.switches.items() if not v]
                if on_switches:
                    home_parts.append(f"  スイッチ: {', '.join(on_switches)} ON")
                if off_switches:
                    home_parts.append(f"  スイッチ: {', '.join(off_switches)} OFF")

            # Binary sensors
            _DEVICE_CLASS_JA = {
                "door": "ドア", "window": "窓", "moisture": "水漏れ",
                "vibration": "振動", "motion": "モーション", "occupancy": "在室",
            }
            for bs in hd.binary_sensors.values():
                if bs.device_class == "moisture":
                    name = bs.entity_id.split(".")[-1] if "." in bs.entity_id else bs.entity_id
                    status = "検知" if bs.state else "正常"
                    prefix = "⚠ " if bs.state else ""
                    dc_ja = _DEVICE_CLASS_JA.get(bs.device_class, bs.device_class)
                    home_parts.append(f"  {prefix}{dc_ja}: {name} {status}")
                elif bs.state:
                    name = bs.entity_id.split(".")[-1] if "." in bs.entity_id else bs.entity_id
                    dc_ja = _DEVICE_CLASS_JA.get(bs.device_class, bs.device_class)
                    home_parts.append(f"  {dc_ja}: {name} 検知中")

            # HA sensors (power, air quality)
            for s in hd.sensors.values():
                name = s.entity_id.split(".")[-1] if "." in s.entity_id else s.entity_id
                if s.device_class == "power" and s.value > 0:
                    home_parts.append(f"  電力: {name} {s.value:.0f}{s.unit or 'W'}")
                elif s.device_class in ("carbon_dioxide", "pm25", "voc"):
                    dc_labels = {"carbon_dioxide": "CO2", "pm25": "PM2.5", "voc": "VOC"}
                    label = dc_labels.get(s.device_class, s.device_class)
                    home_parts.append(f"  {label}: {name} {s.value:.0f}{s.unit or ''}")

            if not hd.bridge_connected:
                home_parts.append("  ⚠ HAブリッジ: 切断中")
            lines.append("\n".join(home_parts))

        # Weather
        w = self.physical.weather
        if w.last_update > 0:
            condition_ja = {
                "sunny": "晴れ", "clear-night": "晴れ", "cloudy": "曇り",
                "partlycloudy": "曇り時々晴れ", "rainy": "雨", "pouring": "大雨",
                "snowy": "雪", "windy": "強風", "fog": "霧", "lightning": "雷",
            }
            cond = condition_ja.get(w.condition, w.condition)
            weather_parts = [f"### 天気: {cond} {w.temperature:.0f}°C 湿度{w.humidity:.0f}%"]
            rain_soon = [f for f in w.forecast[:4] if f.precipitation_probability > 50]
            if rain_soon:
                weather_parts.append(f"  降水予報: {rain_soon[0].precipitation_probability}% ({rain_soon[0].datetime})")
            lines.append("\n".join(weather_parts))

        # Guest mode
        if self.is_guest_mode:
            remaining = int((self._guest_mode_expires - time.time()) / 60)
            lines.append(f"### ゲストモード: ON (残り{remaining}分)")

        return "\n\n".join(lines)

    def _get_digital_context(self) -> str:
        """Build digital space context (PC, services, GAS, knowledge)."""
        lines = []

        # PC state
        pc = self.pc_state
        if pc.cpu.last_update > 0 or pc.memory.last_update > 0:
            pc_parts = ["### PC"]
            if pc.cpu.last_update > 0:
                pc_parts.append(f"  CPU: {pc.cpu.usage_percent:.0f}% ({pc.cpu.core_count}コア)")
                if pc.cpu.temp_c > 0:
                    pc_parts.append(f"  CPU温度: {pc.cpu.temp_c:.0f}°C")
            if pc.memory.last_update > 0:
                pc_parts.append(f"  メモリ: {pc.memory.used_gb:.1f}/{pc.memory.total_gb:.1f}GB ({pc.memory.percent:.0f}%)")
            if pc.gpu.last_update > 0:
                pc_parts.append(f"  GPU: {pc.gpu.usage_percent:.0f}%, VRAM {pc.gpu.vram_used_gb:.1f}/{pc.gpu.vram_total_gb:.1f}GB")
                if pc.gpu.temp_c > 0:
                    pc_parts.append(f"  GPU温度: {pc.gpu.temp_c:.0f}°C")
            if pc.disk.partitions:
                for p in pc.disk.partitions:
                    pc_parts.append(f"  ディスク({p.mount}): {p.used_gb:.0f}/{p.total_gb:.0f}GB ({p.percent:.0f}%)")
            if not pc.bridge_connected:
                pc_parts.append("  ⚠ OpenClawブリッジ: 切断中")
            lines.append("\n".join(pc_parts))

        # Services state
        if self.services_state.services:
            svc_parts = ["### サービス"]
            for name, svc in self.services_state.services.items():
                if svc.error:
                    svc_parts.append(f"  {name}: ⚠ {svc.summary}")
                else:
                    svc_parts.append(f"  {name}: {svc.summary}")
            lines.append("\n".join(svc_parts))

        # GAS state
        gs = self.gas_state
        if gs.bridge_connected:
            gas_parts = ["### Google連携"]
            now_ts = time.time()
            upcoming = [e for e in gs.calendar_events if e.start_ts > now_ts][:3]
            if upcoming:
                gas_parts.append("  予定:")
                for ev in upcoming:
                    time_str = ev.start.split("T")[1][:5] if "T" in ev.start else ev.start
                    gas_parts.append(f"    - {time_str} {ev.title}")
            else:
                gas_parts.append("  予定: なし")

            overdue = [t for t in gs.tasks if t.is_overdue]
            pending = [t for t in gs.tasks if t.status != "completed"]
            if overdue:
                gas_parts.append(f"  タスク: {len(pending)}件（期限切れ{len(overdue)}件）")
            elif pending:
                gas_parts.append(f"  タスク: {len(pending)}件")

            inbox = gs.gmail_labels.get("INBOX")
            if inbox and inbox.unread > 0:
                gas_parts.append(f"  Gmail未読: {inbox.unread}通")

            long_slots = [s for s in gs.free_slots if s.duration_minutes >= 120]
            if long_slots:
                gas_parts.append(f"  空き時間(2h+): {len(long_slots)}スロット")

            lines.append("\n".join(gas_parts))

        # Knowledge base
        ks = self.knowledge_state
        if ks.bridge_connected:
            kb_parts = ["### ナレッジベース"]
            kb_parts.append(f"  ノート数: {ks.total_notes}")
            if ks.recent_changes:
                last = ks.recent_changes[-1]
                kb_parts.append(f"  最終変更: {last['title']}")
            lines.append("\n".join(kb_parts))

        return "\n\n".join(lines)

    def _get_user_context(self) -> str:
        """Build user state context (occupancy summary + biometrics)."""
        lines = []

        # Occupancy summary (aggregated from zones)
        occupied_zones = {zid: z for zid, z in self.zones.items()
                         if z.occupancy and z.occupancy.count > 0}
        if occupied_zones:
            occ_parts = ["### 在室状態"]
            for zid, z in occupied_zones.items():
                occ = z.occupancy
                status = f"  {zid}: {occ.count}人"
                if occ.activity_class != "unknown":
                    status += f", 活動={occ.activity_class}"
                if occ.posture != "unknown":
                    dur = int(occ.posture_duration_sec / 60)
                    status += f", 姿勢={occ.posture}({dur}分)"
                occ_parts.append(status)
            lines.append("\n".join(occ_parts))

        # Biometrics
        bio = self.biometric_state
        if bio.last_update > 0:
            bio_parts = ["### バイオメトリクス"]
            if bio.heart_rate.bpm is not None:
                hr_str = f"  心拍: {bio.heart_rate.bpm}bpm ({bio.heart_rate.zone})"
                if bio.heart_rate.resting_bpm is not None:
                    hr_str += f", 安静時{bio.heart_rate.resting_bpm}bpm"
                bio_parts.append(hr_str)
            if bio.spo2.percent is not None:
                bio_parts.append(f"  SpO2: {bio.spo2.percent}%")
            if bio.stress.last_update > 0:
                bio_parts.append(f"  ストレス: {bio.stress.category} ({bio.stress.level})")
            if bio.fatigue.last_update > 0:
                bio_parts.append(f"  疲労度: {bio.fatigue.score}/100")
            if bio.sleep.last_update > 0:
                sleep_str = f"  睡眠: {bio.sleep.duration_minutes}分"
                if bio.sleep.quality_score > 0:
                    sleep_str += f" (品質{bio.sleep.quality_score}/100)"
                if bio.sleep.stage != "unknown":
                    sleep_str += f", ステージ={bio.sleep.stage}"
                bio_parts.append(sleep_str)
            if bio.hrv.rmssd_ms is not None:
                bio_parts.append(f"  HRV(RMSSD): {bio.hrv.rmssd_ms}ms")
            if bio.body_temperature.celsius is not None:
                bio_parts.append(f"  体温: {bio.body_temperature.celsius:.1f}°C")
            if bio.respiratory_rate.breaths_per_minute is not None:
                bio_parts.append(f"  呼吸数: {bio.respiratory_rate.breaths_per_minute}回/分")
            if bio.activity.last_update > 0:
                pct = int(bio.activity.goal_progress * 100)
                bio_parts.append(f"  歩数: {bio.activity.steps}/{bio.activity.steps_goal} ({pct}%)")
            if not bio.bridge_connected:
                bio_parts.append("  ⚠ バイオメトリクスブリッジ: 切断中")
            lines.append("\n".join(bio_parts))

        # Screen time
        st = self.user.screen_time
        if st.total_minutes > 0:
            hours = st.total_minutes // 60
            mins = st.total_minutes % 60
            lines.append(f"### スクリーンタイム\n  今日: {hours}h{mins}m")

        return "\n\n".join(lines)
