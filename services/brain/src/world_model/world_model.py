"""
WorldModel — maintains unified zone state from MQTT messages.
Forked from SOMS with HEMS personal topic support.
"""

import os
import re
import time

from loguru import logger

from .data_classes import (
    BinarySensorState,  # noqa: F401 - re-exported for WorldModel mixins
    BiometricState,
    CalendarEvent,  # noqa: F401 - re-exported for WorldModel mixins
    ClimateState,  # noqa: F401 - re-exported for WorldModel mixins
    CoverState,  # noqa: F401 - re-exported for WorldModel mixins
    CPUData,  # noqa: F401 - re-exported for WorldModel mixins
    DigitalSpace,
    DiskData,  # noqa: F401 - re-exported for WorldModel mixins
    DiskPartition,  # noqa: F401 - re-exported for WorldModel mixins
    DriveFile,  # noqa: F401 - re-exported for WorldModel mixins
    Event,  # noqa: F401 - re-exported for WorldModel mixins
    FreeSlot,  # noqa: F401 - re-exported for WorldModel mixins
    GASState,
    GmailLabel,  # noqa: F401 - re-exported for WorldModel mixins
    GoogleTask,  # noqa: F401 - re-exported for WorldModel mixins
    GPUData,  # noqa: F401 - re-exported for WorldModel mixins
    HASensorState,  # noqa: F401 - re-exported for WorldModel mixins
    HeartRateData,  # noqa: F401 - re-exported for WorldModel mixins
    HomeDevicesState,
    KnowledgeState,
    LightState,  # noqa: F401 - re-exported for WorldModel mixins
    MemoryData,  # noqa: F401 - re-exported for WorldModel mixins
    NewsState,
    OccupancyData,  # noqa: F401 - re-exported for WorldModel mixins
    PCState,
    PhysicalSpace,
    ProcessInfo,  # noqa: F401 - re-exported for WorldModel mixins
    ServicesState,
    ServiceStatusData,  # noqa: F401 - re-exported for WorldModel mixins
    SheetData,  # noqa: F401 - re-exported for WorldModel mixins
    ShoppingItemData,  # noqa: F401 - re-exported for WorldModel mixins
    ShoppingState,
    StressData,  # noqa: F401 - re-exported for WorldModel mixins
    UserState,
    WeatherAlert,  # noqa: F401 - re-exported for WorldModel mixins
    WeatherForecast,  # noqa: F401 - re-exported for WorldModel mixins
    WeatherState,
    ZoneState,
)
from .sensor_fusion import (
    ChannelType,  # noqa: F401 - re-exported for WorldModel mixins
    EventCounter,
    SensorFusion,
    StateTracker,
    TrendDetector,
    classify_channel,  # noqa: F401 - re-exported for WorldModel mixins
)
from .sensor_validation import validate_sensor_value  # noqa: F401 - re-exported for WorldModel mixins

# B-2: VIP sender / repo identification for service edge events.
# Comma-separated list. A service event is treated as VIP if its payload's
# `vip` field is true, OR if any configured VIP token is found in the event
# summary / details / data.
_VIP_GMAIL_SENDERS = [s.strip().lower() for s in os.getenv("HEMS_GMAIL_VIP_SENDERS", "").split(",") if s.strip()]
_VIP_GITHUB_REPOS = [s.strip().lower() for s in os.getenv("HEMS_GITHUB_VIP_REPOS", "").split(",") if s.strip()]


def _detect_service_vip(service_name: str, payload: dict) -> bool:
    """Return True if the service event is from a VIP sender or repo."""
    if payload.get("vip"):
        return True
    haystack = " ".join(
        str(payload.get(k, "")) for k in ("summary", "details", "subject", "from", "sender", "repo")
    ).lower()
    if not haystack:
        return False
    if service_name == "gmail":
        return any(s and s in haystack for s in _VIP_GMAIL_SENDERS)
    if service_name == "github":
        return any(s and s in haystack for s in _VIP_GITHUB_REPOS)
    return False


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


# Alert/event thresholds are owned by the single source of truth
# (rules.config.RuleThresholds) and reached via constructor DI
# (`self.thresholds.*`, W2.2/W2.3). No module-level threshold aliases remain.
# rules.config depends only on os/dataclasses/loguru, so importing it here
# introduces no cycle.
from rules.config import RuleThresholds, load_rule_thresholds

# Freshness / degraded-operation thresholds (Group C, ported from SOMS).
# A reading older than ENV_STALE_SEC is annotated as stale in the LLM context.
# A zone with no update for ZONE_BLIND_SEC counts toward system-wide blindness,
# which puts the cognitive loop into observe-only mode (side-effects suppressed).
# These are time-windows, not alert thresholds, and remain env-direct (not in
# RuleThresholds) per the W2.1 design note.
ENV_STALE_SEC = int(os.getenv("HEMS_ENV_STALE_SEC", "300"))  # 5 min
ZONE_BLIND_SEC = int(os.getenv("HEMS_ZONE_BLIND_SEC", "300"))  # 5 min


from .context_builder import ContextBuilderMixin
from .digital_updates import DigitalUpdatesMixin
from .mqtt_router import MqttRouterMixin
from .physical_updates import PhysicalUpdatesMixin
from .presence import PresenceMixin
from .user_updates import UserUpdatesMixin


class WorldModel(
    MqttRouterMixin,
    PhysicalUpdatesMixin,
    DigitalUpdatesMixin,
    UserUpdatesMixin,
    ContextBuilderMixin,
    PresenceMixin,
):
    # Default suppression duration (seconds) per alert type.
    # Slow-changing conditions get longer suppression to avoid duplicate tasks
    # while the physical environment slowly responds (e.g., AC cooling a room).
    SUPPRESSION_DEFAULTS: dict[str, float] = {
        "temp_high": 1800,  # 30 min — AC takes time to cool
        "temp_low": 1800,  # 30 min — heating takes time
        "co2_high": 600,  # 10 min — ventilation is faster
        "co2_critical": 600,  # 10 min
    }

    def __init__(self, thresholds: RuleThresholds | None = None):
        # Single source of truth for alert thresholds (constructor DI, W2.2).
        # Falls back to env-loaded defaults when not injected.
        self.thresholds: RuleThresholds = thresholds or load_rule_thresholds()

        # Tri-domain architecture
        self.physical = PhysicalSpace()
        self.digital = DigitalSpace()
        self.user = UserState()

        self._sensor_fusions: dict[str, SensorFusion] = {}
        self._event_counter = EventCounter()
        self._state_tracker = StateTracker()
        self._trend_detector = TrendDetector()
        self.event_writer = None  # Set by Brain if event_store is available

        # VLM model swap coordination flag — brain skips LLM calls when True
        self.vlm_model_swap_active: bool = False
        # B-3: VLM swap stats — outage detection
        self.vlm_swap_stats: dict = {
            "last_swap_start_ts": 0.0,
            "last_swap_end_ts": 0.0,
            "last_swap_duration_sec": 0.0,
            "success_count": 0,
            "failure_count": 0,
            "longest_swap_sec": 0.0,
        }

        # Guest mode: suppresses personal rules (biometric, etc.) for privacy
        self._guest_mode_expiry: float = 0

        # Alert suppression: {(zone_id, alert_type): expiry_timestamp}
        # Prevents repeated task creation for slow-changing conditions.
        self._suppressed_alerts: dict[tuple, float] = {}

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

    @property
    def news_state(self) -> NewsState:
        return self.digital.news_state

    @news_state.setter
    def news_state(self, value: NewsState):
        self.digital.news_state = value

    @property
    def shopping_state(self) -> ShoppingState:
        return self.digital.shopping_state

    @shopping_state.setter
    def shopping_state(self, value: ShoppingState):
        self.digital.shopping_state = value

    @property
    def weather(self) -> WeatherState:
        return self.physical.weather

    @weather.setter
    def weather(self, value: WeatherState):
        self.physical.weather = value

    @property
    def is_guest_mode(self) -> bool:
        return time.time() < self._guest_mode_expiry

    def set_guest_mode(self, enabled: bool, duration_hours: float = 0):
        if enabled:
            self._guest_mode_expiry = time.time() + (duration_hours * 3600)
        else:
            self._guest_mode_expiry = 0

    def suppress_alert(self, zone_id: str, alert_type: str, duration: float = None):
        """Suppress an alert for a zone after a task has been created for it.

        Prevents the LLM from creating duplicate tasks while the physical
        environment slowly responds (e.g., AC cooling a room after task created).
        Auto-clears when sensor readings return to normal range.
        """
        if duration is None:
            duration = self.SUPPRESSION_DEFAULTS.get(alert_type, 1800)
        self._suppressed_alerts[(zone_id, alert_type)] = time.time() + duration
        logger.debug(f"Alert suppressed: zone={zone_id} type={alert_type} duration={duration}s")

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

    def get_zone(self, zone_id: str) -> ZoneState | None:
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

    # --- Presence / occupancy reconciliation ─────────────────────────
    # Camera person_count is the strongest signal, but often unavailable
    # (no camera in zone, offline, VLM disabled). Fall back through:
    # presence_state (HA/SwitchBot/Zigbee binary), recent motion events,
    # PC activity, and biometric heart rate. Recorded sources let the
    # LLM tell why the system thinks someone is home.

    PRESENCE_MOTION_RECENT_SEC = 180  # motion event count as "recent" for 3 min
    PRESENCE_BIOMETRIC_FRESH_SEC = 300  # HR freshness window (5 min)
    PRESENCE_PC_FRESH_SEC = 180  # PC metric freshness (3 min)
    PRESENCE_PC_CPU_ACTIVE = 10.0  # CPU% above which the PC counts as "active"
