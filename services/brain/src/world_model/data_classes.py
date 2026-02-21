"""
Data classes for HEMS WorldModel — zone state, environment, events, PC state,
Home Assistant smart home devices, biometrics, and tri-domain facades.
"""
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class EnvironmentData:
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    co2: Optional[float] = None
    pressure: Optional[float] = None
    light: Optional[float] = None
    voc: Optional[float] = None
    last_update: float = 0

    @property
    def is_stuffy(self) -> bool:
        """CO2 concentration exceeds 1000ppm threshold."""
        return self.co2 is not None and self.co2 > 1000

    @property
    def thermal_comfort(self) -> str:
        """Thermal comfort level: cold | comfortable | hot."""
        if self.temperature is None:
            return "unknown"
        if self.temperature < 18:
            return "cold"
        elif self.temperature > 26:
            return "hot"
        return "comfortable"


@dataclass
class OccupancyData:
    count: int = 0
    last_update: float = 0
    # Perception ActivityMonitor data
    activity_level: float = 0.0            # 0.0-1.0 (short-term motion)
    activity_class: str = "unknown"        # "idle"|"low"|"moderate"|"high"
    posture_duration_sec: float = 0.0      # Current posture duration (seconds)
    posture_status: str = "unknown"        # "changing"|"mostly_static"|"static"


@dataclass
class DeviceState:
    device_id: str = ""
    state: dict = field(default_factory=dict)
    last_update: float = 0


@dataclass
class Event:
    event_type: str = ""
    description: str = ""
    severity: int = 0  # 0=info, 1=warning, 2=critical
    timestamp: float = field(default_factory=time.time)
    zone: str = ""
    data: dict = field(default_factory=dict)

    @property
    def auto_description(self) -> str:
        """Auto-generated event description based on event_type and data.

        Falls back to the stored description field if no template matches.
        """
        if self.event_type == "person_entered":
            return f"{self.data.get('count', 0)}人が入室しました"
        elif self.event_type == "person_exited":
            return f"{self.data.get('count', 0)}人が退室しました"
        elif self.event_type in ("co2_threshold_exceeded", "co2_high"):
            return f"CO2濃度が{self.data.get('value', self.data.get('co2', 0))}ppmに達しました（換気推奨）"
        elif self.event_type == "co2_critical":
            return f"CO2危険レベル: {self.data.get('co2', 0)}ppm"
        elif self.event_type == "temp_spike":
            return f"気温が急上昇しました（{self.data.get('value', 0)}℃）"
        elif self.event_type in ("temp_high", "temp_low"):
            return self.description or f"イベント: {self.event_type}"
        elif self.event_type == "sedentary_alert":
            minutes = int(self.data.get('duration_sec', self.data.get('duration_minutes', 0) * 60) / 60)
            return f"同じ姿勢で{minutes}分以上座り続けています"
        elif self.event_type == "sensor_tamper":
            channel = self.data.get('channel', '?')
            change = self.data.get('change', 0)
            return f"センサー異常: {channel}が急変({change:.1f}変化)"
        elif self.event_type == "door_opened":
            return f"ドアが開きました ({self.data.get('device_id', '')})"
        elif self.event_type == "door_closed":
            return f"ドアが閉まりました ({self.data.get('device_id', '')})"
        elif self.event_type == "task_report":
            status_labels = {
                "no_issue": "問題なし",
                "resolved": "対応済み",
                "needs_followup": "要追加対応",
                "cannot_resolve": "対応不可",
            }
            title = self.data.get("title", "タスク")
            status = status_labels.get(
                self.data.get("report_status", ""),
                self.data.get("report_status", ""),
            )
            note = self.data.get("completion_note", "")
            desc = f"「{title}」→ {status}"
            if note:
                desc += f": {note}"
            return desc
        # Fall back to stored description string
        return self.description or f"イベント: {self.event_type}"


@dataclass
class ZoneState:
    zone_id: str = ""
    environment: EnvironmentData = field(default_factory=EnvironmentData)
    occupancy: OccupancyData = field(default_factory=OccupancyData)
    devices: dict[str, DeviceState] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    max_events: int = 50

    def add_event(self, event: Event):
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]


# --- Service Status (Service Monitor) ---

@dataclass
class ServiceStatusData:
    name: str = ""
    available: bool = True
    unread_count: int = 0
    summary: str = ""
    details: dict = field(default_factory=dict)
    last_check: float = 0
    error: str | None = None


@dataclass
class ServicesState:
    services: dict[str, ServiceStatusData] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    max_events: int = 20

    def add_event(self, event: Event):
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]


# --- Knowledge State (Obsidian integration) ---

@dataclass
class KnowledgeState:
    total_notes: int = 0
    indexed: int = 0
    recent_changes: list[dict] = field(default_factory=list)  # [{path, title, action}]
    bridge_connected: bool = False
    events: list[Event] = field(default_factory=list)
    max_events: int = 20
    max_recent: int = 5

    def add_event(self, event: Event):
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

    def add_recent_change(self, change: dict):
        self.recent_changes.append(change)
        if len(self.recent_changes) > self.max_recent:
            self.recent_changes = self.recent_changes[-self.max_recent:]


# --- PC State (OpenClaw integration) ---

@dataclass
class CPUData:
    usage_percent: float = 0
    core_count: int = 0
    freq_mhz: float = 0
    temp_c: float = 0
    last_update: float = 0


@dataclass
class MemoryData:
    used_gb: float = 0
    total_gb: float = 0
    percent: float = 0
    last_update: float = 0


@dataclass
class GPUData:
    usage_percent: float = 0
    vram_used_gb: float = 0
    vram_total_gb: float = 0
    temp_c: float = 0
    last_update: float = 0


@dataclass
class DiskPartition:
    mount: str = ""
    used_gb: float = 0
    total_gb: float = 0
    percent: float = 0


@dataclass
class DiskData:
    partitions: list[DiskPartition] = field(default_factory=list)
    last_update: float = 0


@dataclass
class ProcessInfo:
    pid: int = 0
    name: str = ""
    cpu_percent: float = 0
    mem_mb: float = 0


@dataclass
class PCState:
    cpu: CPUData = field(default_factory=CPUData)
    memory: MemoryData = field(default_factory=MemoryData)
    gpu: GPUData = field(default_factory=GPUData)
    disk: DiskData = field(default_factory=DiskData)
    top_processes: list[ProcessInfo] = field(default_factory=list)
    bridge_connected: bool = False
    events: list[Event] = field(default_factory=list)
    max_events: int = 50

    def add_event(self, event: Event):
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]


# --- GAS State (Google Apps Script integration) ---

@dataclass
class CalendarEvent:
    id: str = ""
    title: str = ""
    start: str = ""
    end: str = ""
    location: str = ""
    calendar_name: str = ""
    is_all_day: bool = False
    description: str = ""
    start_ts: float = 0  # UNIX timestamp (parsed)
    end_ts: float = 0


@dataclass
class FreeSlot:
    start: str = ""
    end: str = ""
    duration_minutes: int = 0


@dataclass
class GoogleTask:
    id: str = ""
    title: str = ""
    notes: str = ""
    due: str = ""
    status: str = ""
    list_name: str = ""
    is_overdue: bool = False


@dataclass
class GmailLabel:
    name: str = ""
    unread: int = 0
    total: int = 0


@dataclass
class DriveFile:
    name: str = ""
    mime_type: str = ""
    modified_time: str = ""
    url: str = ""


@dataclass
class SheetData:
    name: str = ""
    values: list = field(default_factory=list)
    headers: list = field(default_factory=list)
    last_update: float = 0


@dataclass
class GASState:
    calendar_events: list[CalendarEvent] = field(default_factory=list)
    free_slots: list[FreeSlot] = field(default_factory=list)
    tasks: list[GoogleTask] = field(default_factory=list)
    gmail_labels: dict[str, GmailLabel] = field(default_factory=dict)
    gmail_recent: list[dict] = field(default_factory=list)
    sheets: dict[str, SheetData] = field(default_factory=dict)
    drive_recent: list[DriveFile] = field(default_factory=list)
    bridge_connected: bool = False
    last_calendar_update: float = 0
    last_tasks_update: float = 0
    last_gmail_update: float = 0
    events: list[Event] = field(default_factory=list)
    max_events: int = 30

    def add_event(self, event: Event):
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]


# --- Home Devices State (Home Assistant integration) ---

@dataclass
class LightState:
    entity_id: str = ""
    on: bool = False
    brightness: int = 0        # 0-255
    color_temp: int = 0        # mirek
    last_update: float = 0


@dataclass
class ClimateState:
    entity_id: str = ""
    mode: str = "off"          # off, cool, heat, dry, fan_only, auto
    target_temp: float = 0
    current_temp: float = 0
    fan_mode: str = "auto"
    last_update: float = 0


@dataclass
class CoverState:
    entity_id: str = ""
    position: int = 0          # 0=closed, 100=open
    is_open: bool = False
    last_update: float = 0


@dataclass
class HomeDevicesState:
    lights: dict[str, LightState] = field(default_factory=dict)
    climates: dict[str, ClimateState] = field(default_factory=dict)
    covers: dict[str, CoverState] = field(default_factory=dict)
    switches: dict[str, bool] = field(default_factory=dict)
    bridge_connected: bool = False
    events: list[Event] = field(default_factory=list)
    max_events: int = 30

    def add_event(self, event: Event):
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]


# --- Biometric State (Smartband / Gadgetbridge integration) ---

@dataclass
class HeartRateData:
    bpm: Optional[int] = None
    resting_bpm: Optional[int] = None
    zone: str = "unknown"  # rest | fat_burn | cardio | peak
    last_update: float = 0

    @staticmethod
    def classify_zone(bpm: int) -> str:
        if bpm < 60:
            return "rest"
        elif bpm < 120:
            return "fat_burn"
        elif bpm < 150:
            return "cardio"
        return "peak"


@dataclass
class SleepData:
    stage: str = "unknown"  # awake | light | deep | rem
    duration_minutes: int = 0
    deep_minutes: int = 0
    rem_minutes: int = 0
    light_minutes: int = 0
    quality_score: int = 0  # 0-100
    sleep_start_ts: float = 0
    sleep_end_ts: float = 0
    last_update: float = 0


@dataclass
class ActivityData:
    steps: int = 0
    steps_goal: int = 10000
    calories: int = 0
    active_minutes: int = 0
    level: str = "rest"  # rest | light | moderate | vigorous
    last_update: float = 0

    @property
    def goal_progress(self) -> float:
        if self.steps_goal <= 0:
            return 0.0
        return min(self.steps / self.steps_goal, 1.0)


@dataclass
class StressData:
    level: int = 0  # 0-100
    category: str = "unknown"  # relaxed | normal | moderate | high
    last_update: float = 0

    @staticmethod
    def classify_category(level: int) -> str:
        if level < 25:
            return "relaxed"
        elif level < 50:
            return "normal"
        elif level < 75:
            return "moderate"
        return "high"


@dataclass
class FatigueData:
    score: int = 0  # 0-100 (higher = more fatigued)
    factors: list[str] = field(default_factory=list)
    last_update: float = 0


@dataclass
class SpO2Data:
    percent: Optional[int] = None
    last_update: float = 0


@dataclass
class HRVData:
    rmssd_ms: Optional[int] = None  # Root Mean Square of Successive Differences
    last_update: float = 0


@dataclass
class BodyTemperatureData:
    celsius: Optional[float] = None
    last_update: float = 0


@dataclass
class RespiratoryRateData:
    breaths_per_minute: Optional[int] = None
    last_update: float = 0


@dataclass
class ScreenTimeData:
    total_minutes: int = 0
    active_app: str = ""
    session_start_ts: float = 0
    last_update: float = 0


@dataclass
class BiometricState:
    heart_rate: HeartRateData = field(default_factory=HeartRateData)
    hrv: HRVData = field(default_factory=HRVData)
    body_temperature: BodyTemperatureData = field(default_factory=BodyTemperatureData)
    respiratory_rate: RespiratoryRateData = field(default_factory=RespiratoryRateData)
    sleep: SleepData = field(default_factory=SleepData)
    activity: ActivityData = field(default_factory=ActivityData)
    stress: StressData = field(default_factory=StressData)
    fatigue: FatigueData = field(default_factory=FatigueData)
    spo2: SpO2Data = field(default_factory=SpO2Data)
    provider: str = ""
    bridge_connected: bool = False
    events: list[Event] = field(default_factory=list)
    max_events: int = 30

    def add_event(self, event: Event):
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

    @property
    def last_update(self) -> float:
        return max(
            self.heart_rate.last_update,
            self.hrv.last_update,
            self.body_temperature.last_update,
            self.respiratory_rate.last_update,
            self.sleep.last_update,
            self.activity.last_update,
            self.stress.last_update,
            self.fatigue.last_update,
            self.spo2.last_update,
        )


# --- Tri-Domain Facades ---

@dataclass
class PhysicalSpace:
    """Physical environment domain — zones and smart home devices."""
    zones: dict[str, ZoneState] = field(default_factory=dict)
    home_devices: HomeDevicesState = field(default_factory=HomeDevicesState)


@dataclass
class DigitalSpace:
    """Digital environment domain — PC, services, GAS, knowledge."""
    pc_state: PCState = field(default_factory=PCState)
    services_state: ServicesState = field(default_factory=ServicesState)
    gas_state: GASState = field(default_factory=GASState)
    knowledge_state: KnowledgeState = field(default_factory=KnowledgeState)


@dataclass
class UserState:
    """User state domain — biometrics and personal data."""
    biometrics: BiometricState = field(default_factory=BiometricState)
    screen_time: ScreenTimeData = field(default_factory=ScreenTimeData)
