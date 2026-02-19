"""
WorldModel — maintains unified zone state from MQTT messages.
Forked from SOMS with HEMS personal topic support.
"""
import os
import time
import logging
from typing import Optional
from .data_classes import (
    ZoneState, EnvironmentData, OccupancyData, Event,
    PCState, CPUData, MemoryData, GPUData, DiskData, DiskPartition, ProcessInfo,
    ServicesState, ServiceStatusData,
    KnowledgeState,
    GASState, CalendarEvent, FreeSlot, GoogleTask, GmailLabel, DriveFile, SheetData,
)
from .sensor_fusion import SensorFusion

logger = logging.getLogger(__name__)

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
        self.zones: dict[str, ZoneState] = {}
        self.pc_state: PCState = PCState()
        self.services_state: ServicesState = ServicesState()
        self.knowledge_state: KnowledgeState = KnowledgeState()
        self.gas_state: GASState = GASState()
        self._sensor_fusions: dict[str, SensorFusion] = {}
        self.event_writer = None  # Set by Brain if event_store is available

        # Alert suppression: {(zone_id, alert_type): expiry_timestamp}
        # Prevents repeated task creation for slow-changing conditions.
        self._suppressed_alerts: dict[tuple, float] = {}

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
            zone.add_event(Event(
                event_type="task_report",
                description=f"タスク報告: {payload.get('title', '')} ({payload.get('report_status', '')})",
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
                name=payload.get("name", service_name),
                available=payload.get("available", True),
                unread_count=payload.get("unread_count", 0),
                summary=payload.get("summary", ""),
                details=payload.get("details", {}),
                last_check=payload.get("last_check", time.time()),
                error=payload.get("error"),
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
                description=payload.get("summary", f"{service_name} event"),
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
                "path": payload.get("path", ""),
                "title": payload.get("title", ""),
                "action": payload.get("action", ""),
            }
            ks.add_recent_change(change)
            ks.add_event(Event(
                event_type="note_changed",
                description=f"ノート変更: {change['title']} ({change['action']})",
                severity=0,
                data=payload,
            ))

    def get_llm_context(self) -> str:
        """Build text context for LLM from current world state."""
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
                if zone.occupancy.posture_status != "unknown":
                    duration_min = int(zone.occupancy.posture_duration_sec / 60)
                    parts.append(f"  姿勢: {zone.occupancy.posture_status} ({duration_min}分)")

            lines.append("\n".join(parts))

        # PC state (only if bridge has sent data)
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

        # Services state (only if any service data exists)
        if self.services_state.services:
            svc_parts = ["### サービス"]
            for name, svc in self.services_state.services.items():
                if svc.error:
                    svc_parts.append(f"  {name}: ⚠ {svc.summary}")
                else:
                    svc_parts.append(f"  {name}: {svc.summary}")
            lines.append("\n".join(svc_parts))

        # GAS state (lightweight summary)
        gs = self.gas_state
        if gs.bridge_connected:
            gas_parts = ["### Google連携"]
            # Next 3 upcoming events
            now_ts = time.time()
            upcoming = [e for e in gs.calendar_events if e.start_ts > now_ts][:3]
            if upcoming:
                gas_parts.append("  予定:")
                for ev in upcoming:
                    time_str = ev.start.split("T")[1][:5] if "T" in ev.start else ev.start
                    gas_parts.append(f"    - {time_str} {ev.title}")
            else:
                gas_parts.append("  予定: なし")

            # Tasks summary
            overdue = [t for t in gs.tasks if t.is_overdue]
            pending = [t for t in gs.tasks if t.status != "completed"]
            if overdue:
                gas_parts.append(f"  タスク: {len(pending)}件（期限切れ{len(overdue)}件）")
            elif pending:
                gas_parts.append(f"  タスク: {len(pending)}件")

            # Gmail unread
            inbox = gs.gmail_labels.get("INBOX")
            if inbox and inbox.unread > 0:
                gas_parts.append(f"  Gmail未読: {inbox.unread}通")

            # Free slots
            long_slots = [s for s in gs.free_slots if s.duration_minutes >= 120]
            if long_slots:
                gas_parts.append(f"  空き時間(2h+): {len(long_slots)}スロット")

            lines.append("\n".join(gas_parts))

        # Knowledge base (lightweight metadata only)
        ks = self.knowledge_state
        if ks.bridge_connected:
            kb_parts = ["### ナレッジベース"]
            kb_parts.append(f"  ノート数: {ks.total_notes}")
            if ks.recent_changes:
                last = ks.recent_changes[-1]
                kb_parts.append(f"  最終変更: {last['title']}")
            lines.append("\n".join(kb_parts))

        if not lines:
            return ""
        return "\n\n".join(lines)
