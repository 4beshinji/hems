import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hems_common.biometric import (
    BiometricAggregation as BiometricAggregation,
)
from hems_common.biometric import (
    BiometricMetrics as BiometricMetrics,
)
from hems_common.biometric import (
    BiometricObservationIn as BiometricObservationIn,
)
from hems_common.validation import validate_device_ref

# ---------------------------------------------------------------------------
# Device identifier validation
# ---------------------------------------------------------------------------

# --- Task ---


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    location: str | None = None
    expires_at: datetime | None = None
    task_type: list[str] | None = None
    urgency: int = 2
    zone: str | None = None
    estimated_duration: int = 10
    announcement_audio_url: str | None = None
    announcement_text: str | None = None
    completion_audio_url: str | None = None
    completion_text: str | None = None
    cognitive_load: int | None = None
    preferred_time_slot: str | None = None
    deadline: datetime | None = None
    source: str | None = None
    source_ref: str | None = None
    confidence: float | None = None
    proposal_status: str | None = None


class Task(BaseModel):
    id: int
    title: str
    description: str | None = None
    location: str | None = None
    is_completed: bool = False
    is_queued: bool = False
    created_at: datetime | None = None
    completed_at: datetime | None = None
    dispatched_at: datetime | None = None
    expires_at: datetime | None = None
    task_type: list[str] | None = None
    urgency: int = 2
    zone: str | None = None
    estimated_duration: int = 10
    announcement_audio_url: str | None = None
    announcement_text: str | None = None
    completion_audio_url: str | None = None
    completion_text: str | None = None
    assigned_to: int | None = None
    accepted_at: datetime | None = None
    last_reminded_at: datetime | None = None
    report_status: str | None = None
    completion_note: str | None = None
    cognitive_load: int | None = None
    preferred_time_slot: str | None = None
    deadline: datetime | None = None
    source: str | None = None
    source_ref: str | None = None
    confidence: float | None = None
    proposal_status: str | None = None
    dismissed_at: datetime | None = None
    dismiss_reason: str | None = None
    locked_start: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TaskComplete(BaseModel):
    report_status: str | None = None
    completion_note: str | None = None


class TaskAccept(BaseModel):
    user_id: int | None = None


class TaskDismiss(BaseModel):
    reason: str | None = None


class TaskLock(BaseModel):
    locked_start: datetime


# --- Timeline ---


class ScheduledBlock(BaseModel):
    id: int
    date: str
    start_ts: datetime
    end_ts: datetime
    kind: str
    ref_task_id: int | None = None
    ref_calendar_event_id: str | None = None
    title: str
    location: str | None = None
    is_locked: bool = False
    travel_buffer_minutes: int = 0
    generated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ScheduledBlockIn(BaseModel):
    start_ts: datetime
    end_ts: datetime
    kind: str
    ref_task_id: int | None = None
    ref_calendar_event_id: str | None = None
    title: str
    location: str | None = None
    is_locked: bool = False
    travel_buffer_minutes: int = 0


class TimelineRegenerate(BaseModel):
    date: str
    blocks: list[ScheduledBlockIn]


class TimelineResponse(BaseModel):
    date: str
    blocks: list[ScheduledBlock]
    generated_at: datetime | None = None


# --- SystemStats ---


class SystemStatsResponse(BaseModel):
    tasks_completed: int = 0
    tasks_created: int = 0
    tasks_active: int = 0
    tasks_queued: int = 0
    tasks_completed_last_hour: int = 0


# --- VoiceEvent ---


class VoiceEventCreate(BaseModel):
    message: str
    audio_url: str
    zone: str | None = None
    tone: str = "neutral"
    motion_id: str | None = None


class VoiceEvent(BaseModel):
    id: int
    message: str
    audio_url: str
    zone: str | None = None
    tone: str = "neutral"
    motion_id: str | None = None
    created_at: datetime | None = None
    feedback_score: float | None = None

    model_config = ConfigDict(from_attributes=True)


# --- User ---


class UserCreate(BaseModel):
    username: str
    display_name: str | None = None


class UserUpdate(BaseModel):
    username: str | None = None
    display_name: str | None = None


class User(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    is_active: bool = True
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# --- Zone / Sensor ---


class EnvironmentData(BaseModel):
    temperature: float | None = None
    humidity: float | None = None
    co2: float | None = None
    pressure: float | None = None
    light: float | None = None
    voc: float | None = None
    last_update: float | None = None


class OccupancyData(BaseModel):
    count: int = 0
    last_update: float | None = None


class ZoneSnapshot(BaseModel):
    zone_id: str
    environment: EnvironmentData = EnvironmentData()
    occupancy: OccupancyData = OccupancyData()
    events: list[dict] = []


class ZonesUpdate(BaseModel):
    zones: list[ZoneSnapshot]


# --- Shopping List ---


class ShoppingItemCreate(BaseModel):
    name: str
    category: str | None = None
    quantity: int = 1
    unit: str | None = None
    store: str | None = None
    store_category: str | None = None
    price: int | None = None
    is_recurring: bool = False
    recurrence_days: int | None = None
    notes: str | None = None
    priority: int = 1
    created_by: str = "user"


class ShoppingItemUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    quantity: int | None = None
    unit: str | None = None
    store: str | None = None
    store_category: str | None = None
    price: int | None = None
    is_recurring: bool | None = None
    recurrence_days: int | None = None
    notes: str | None = None
    priority: int | None = None


class ShoppingItemPatch(BaseModel):
    """Partial update — only fields explicitly provided are written."""

    name: str | None = None
    category: str | None = None
    quantity: int | None = None
    unit: str | None = None
    store: str | None = None
    store_category: str | None = None
    price: int | None = None
    is_recurring: bool | None = None
    recurrence_days: int | None = None
    notes: str | None = None
    priority: int | None = None

    model_config = ConfigDict(extra="forbid")


class ShoppingItem(BaseModel):
    id: int
    name: str
    category: str | None = None
    quantity: int = 1
    unit: str | None = None
    store: str | None = None
    store_category: str | None = None
    price: int | None = None
    is_purchased: bool = False
    is_recurring: bool = False
    recurrence_days: int | None = None
    last_purchased_at: datetime | None = None
    next_purchase_at: datetime | None = None
    notes: str | None = None
    priority: int = 1
    created_at: datetime | None = None
    purchased_at: datetime | None = None
    created_by: str = "user"
    share_token: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PurchaseHistory(BaseModel):
    id: int
    item_name: str
    category: str | None = None
    store: str | None = None
    price: int | None = None
    quantity: int = 1
    purchased_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ShoppingStats(BaseModel):
    total_items: int = 0
    purchased_items: int = 0
    pending_items: int = 0
    total_spent_this_month: int = 0
    category_breakdown: dict = {}


class ShoppingShareResponse(BaseModel):
    share_url: str
    token: str
    items: list[ShoppingItem] = []


# --- Chat ---


class ChatMessageSend(BaseModel):
    content: str
    conversation_id: int | None = None
    tts: bool | None = None  # None=auto (short responses), True=force, False=skip


class ChatMessage(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    audio_url: str | None = None
    tool_calls_json: str | None = None
    metadata_json: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatResponse(BaseModel):
    user_message: ChatMessage
    assistant_message: ChatMessage
    conversation_id: int


class ConversationSummary(BaseModel):
    id: int
    title: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


# --- Device Registry ---


class DeviceBase(BaseModel):
    device_id: str
    vendor: str
    vendor_ref: str | None = None
    kind: str = "actuator"  # sensor|actuator|both
    device_class: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    units: dict = Field(default_factory=dict)
    display_name: str | None = None
    zone: str | None = None
    location: str | None = None
    purpose: str | None = None
    description: str | None = None
    model_id: str | None = None
    manufacturer: str | None = None
    icon: str | None = None
    battery_pct: int | None = None
    link_quality: int | None = None
    is_enabled: bool = True
    notes: str | None = None
    metadata_json: str | None = None

    @field_validator("device_id")
    @classmethod
    def _check_device_id(cls, v: str) -> str:
        return validate_device_ref(v, "device_id")

    @field_validator("vendor_ref")
    @classmethod
    def _check_vendor_ref(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_device_ref(v, "vendor_ref")


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    # All fields optional for partial update — metadata editing from UI
    vendor_ref: str | None = None
    kind: str | None = None
    device_class: str | None = None
    capabilities: list[str] | None = None
    channels: list[str] | None = None
    units: dict | None = None
    display_name: str | None = None
    zone: str | None = None
    location: str | None = None
    purpose: str | None = None
    description: str | None = None
    model_id: str | None = None
    manufacturer: str | None = None
    icon: str | None = None
    is_enabled: bool | None = None
    notes: str | None = None
    metadata_json: str | None = None

    @field_validator("vendor_ref")
    @classmethod
    def _check_vendor_ref(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_device_ref(v, "vendor_ref")


class Device(DeviceBase):
    id: int
    last_state: dict = Field(default_factory=dict)
    last_value: dict = Field(default_factory=dict)
    last_seen: datetime | None = None
    last_seen_reported: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DeviceHeartbeat(BaseModel):
    """Brain push: create-or-update on sensor/actuator activity."""

    device_id: str
    vendor: str
    vendor_ref: str | None = None
    kind: str | None = None
    device_class: str | None = None
    capabilities: list[str] | None = None
    channels: list[str] | None = None
    units: dict | None = None
    zone: str | None = None
    display_name: str | None = None
    description: str | None = None
    model_id: str | None = None
    manufacturer: str | None = None
    last_state: dict | None = None
    last_value: dict | None = None
    battery_pct: int | None = None
    link_quality: int | None = None
    last_seen_reported: float | None = None  # epoch seconds (Z2M last_seen)

    @field_validator("device_id")
    @classmethod
    def _check_device_id(cls, v: str) -> str:
        return validate_device_ref(v, "device_id")

    @field_validator("vendor_ref")
    @classmethod
    def _check_vendor_ref(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_device_ref(v, "vendor_ref")


class DeviceControlRequest(BaseModel):
    """UI manual control: forwarded via Brain to the physical device."""

    action: str  # on|off|toggle|set_brightness|set_color_temp|set_position|pulse|ir_send
    params: dict = Field(default_factory=dict)


class DeviceControlResponse(BaseModel):
    success: bool
    result: str | None = None
    error: str | None = None


class ZigbeePermitJoinRequest(BaseModel):
    """Open/close the Z2M coordinator for new device pairing."""

    enable: bool
    duration_s: int = Field(default=60, ge=0, le=3600, description="Auto-close after N seconds (0 = open until closed)")


# --- Scene ---


class SceneAction(BaseModel):
    device_id: str
    action: str
    params: dict = Field(default_factory=dict)
    delay_s: int = 0


class SceneBase(BaseModel):
    name: str  # programmatic ID "wake_up"
    display_name: str
    description: str | None = None
    actions: list[SceneAction] = Field(default_factory=list)
    is_enabled: bool = True


class SceneCreate(SceneBase):
    pass


class SceneUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    actions: list[SceneAction] | None = None
    is_enabled: bool | None = None


class Scene(SceneBase):
    id: int
    last_executed_at: datetime | None = None
    execution_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SceneExecuteResponse(BaseModel):
    success: bool
    executed: int
    errors: list[str] = Field(default_factory=list)


# --- AutomationRule ---


class AutomationRuleBase(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    trigger_type: str  # sensor_threshold|schedule|event|device_state
    trigger_config: dict = Field(default_factory=dict)
    actions: list[SceneAction] = Field(default_factory=list)
    cooldown_s: int = 600
    mode: str = "direct"  # direct|llm_review
    require_confirm: bool = False
    risk_tier: str = "low"  # safe|low|medium|high|critical
    reversibility: str = "reversible"  # reversible|compensatable|irreversible
    approval_required: bool = False
    auto_rollback_window_seconds: int = 300


class AutomationRuleCreate(AutomationRuleBase):
    pass


class AutomationRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    trigger_type: str | None = None
    trigger_config: dict | None = None
    actions: list[SceneAction] | None = None
    cooldown_s: int | None = None
    mode: str | None = None
    require_confirm: bool | None = None
    risk_tier: str | None = None
    reversibility: str | None = None
    approval_required: bool | None = None
    auto_rollback_window_seconds: int | None = None


class AutomationRule(AutomationRuleBase):
    id: int
    last_fired_at: datetime | None = None
    fire_count: int = 0
    last_evaluation_ts: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AutomationRuleFireUpdate(BaseModel):
    """Brain → backend: record successful firing stats."""

    last_fired_at: datetime
    fire_count: int
    last_evaluation_ts: float | None = None


# --- Approval / HITL ---


class ApprovalBase(BaseModel):
    thread_id: str | None = None
    rule_id: int | None = None
    action_type: str  # device_control|scene|rule_promotion|config_change
    risk_tier: str = "low"  # safe|low|medium|high|critical
    reversibility: str = "reversible"  # reversible|compensatable|irreversible
    confidence: float | None = None
    proposed_payload: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)


class ApprovalCreate(ApprovalBase):
    pass


class ApprovalDecision(BaseModel):
    decision: str  # approve|reject|modify
    reason: str | None = None
    reviewer_id: str | None = None
    modified_payload: dict | None = None


class Approval(ApprovalBase):
    id: str  # UUID serialized as string
    status: str = "proposed"  # proposed|pending|approved|rejected|modified|expired|rolled_back
    reviewer_id: str | None = None
    decision: str | None = None
    decision_reason: str | None = None
    requested_at: datetime | None = None
    decided_at: datetime | None = None
    expires_at: datetime | None = None
    executed_at: datetime | None = None
    rollback_plan: dict | None = None
    rollback_status: str | None = "none"
    audit_log: list = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("id", mode="before")
    @classmethod
    def _uuid_to_str(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v


class ActionSnapshotBase(BaseModel):
    approval_id: str
    entity_type: str  # device|scene|rule|config
    entity_id: str
    before_state: dict = Field(default_factory=dict)
    after_state: dict | None = None


class ActionSnapshotCreate(ActionSnapshotBase):
    pass


class ActionSnapshot(ActionSnapshotBase):
    id: int
    captured_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("approval_id", mode="before")
    @classmethod
    def _uuid_to_str(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v


class RollbackLogBase(BaseModel):
    approval_id: str
    trigger: str  # human_reject|verification_failure|timeout|policy_violation
    compensation_plan: dict | None = None


class RollbackLogCreate(RollbackLogBase):
    pass


class RollbackLog(RollbackLogBase):
    id: int
    execution_status: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("approval_id", mode="before")
    @classmethod
    def _uuid_to_str(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v


class ConversationDetail(BaseModel):
    id: int
    title: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    messages: list[ChatMessage] = []

    model_config = ConfigDict(from_attributes=True)


# --- FrequentPlace (geofence targets for shopping / location reminders) ---


class FrequentPlaceCreate(BaseModel):
    label: str
    category: str  # drugstore|supermarket|convenience|home_center|other
    lat: float
    lon: float
    radius_m: int = 200
    enabled: bool = True
    cooldown_min: int = 60


class FrequentPlaceUpdate(BaseModel):
    label: str | None = None
    category: str | None = None
    lat: float | None = None
    lon: float | None = None
    radius_m: int | None = None
    enabled: bool | None = None
    cooldown_min: int | None = None


class FrequentPlace(BaseModel):
    id: int
    label: str
    category: str
    lat: float
    lon: float
    radius_m: int = 200
    enabled: bool = True
    cooldown_min: int = 60
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# --- ClassifierCache (brain-side learned classifications) ---


class ClassifierCacheEntry(BaseModel):
    """Shared read/write shape for `/classifier-cache/` endpoints."""

    kind: str  # "shopping" | "event_lead" | ...
    key_hash: str  # sha256(kind + ":" + normalized_input), caller-provided
    value_json: str  # JSON-encoded payload (value semantics owned by brain)
    source: str = "llm"  # seed | llm | user_override | promoted

    model_config = ConfigDict(extra="forbid")


class ClassifierCacheRecord(ClassifierCacheEntry):
    id: int
    hit_count: int = 1
    learned_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, extra="ignore")


# --- Mobile device registration & webhook ---


class MobileDeviceRegisterRequest(BaseModel):
    device_label: str
    platform: str | None = None  # "android" | "ios"


class MobileDeviceRegisterResponse(BaseModel):
    device_id: int
    device_key: str  # issued; client stores securely
    hmac_secret: str  # for state webhook signing
    backend_url: str | None = None
    character_version: str | None = None


class MobileDevice(BaseModel):
    id: int
    device_label: str
    platform: str | None = None
    registered_at: datetime | None = None
    last_seen_at: datetime | None = None
    enabled: bool = True

    model_config = ConfigDict(from_attributes=True)


class MobileLocationReading(BaseModel):
    lat: float
    lon: float
    accuracy_m: float | None = None
    speed_mps: float | None = None
    heading_deg: float | None = None
    provider: str | None = None  # "fused" | "gps" | "network"


class MobileActivityReading(BaseModel):
    kind: str  # "still" | "walking" | "running" | "in_vehicle" | "on_bicycle" | "unknown"
    confidence: int | None = None


class MobileBiometricReading(BaseModel):
    heart_rate: int | None = None
    spo2: int | None = None
    steps: int | None = None
    stress_level: int | None = None
    sleep_duration_minutes: int | None = None


class MobileStateWebhookPayload(BaseModel):
    ts: datetime  # client-provided timestamp
    location: MobileLocationReading | None = None
    activity: MobileActivityReading | None = None
    biometrics: MobileBiometricReading | None = None
    battery_pct: int | None = None
    app_foreground: bool | None = None


class MobileStateWebhookResponse(BaseModel):
    received: bool = True
    published_topics: list[str] = []


# --- Biometric latest snapshot ---


class BiometricHeartRateSnapshot(BaseModel):
    bpm: int
    zone: str | None = None
    resting_bpm: int | None = None


class BiometricSpO2Snapshot(BaseModel):
    percent: int


class BiometricSleepSnapshot(BaseModel):
    stage: str | None = None
    duration_minutes: int | None = None
    deep_minutes: int | None = None
    rem_minutes: int | None = None
    light_minutes: int | None = None
    quality_score: int | None = None


class BiometricActivitySnapshot(BaseModel):
    steps: int | None = None
    steps_goal: int | None = None
    calories: int | None = None
    active_minutes: int | None = None
    level: str | None = None


class BiometricStressSnapshot(BaseModel):
    level: int | None = None
    category: str | None = None


class BiometricFatigueSnapshot(BaseModel):
    score: int | None = None
    factors: list[str] = Field(default_factory=list)


class BiometricSnapshotIn(BaseModel):
    """Brain latest-state projection, with temporary flat-payload compatibility."""

    bridge_connected: bool | None = None
    provider: str = "unknown"
    heart_rate: BiometricHeartRateSnapshot | int | None = None
    spo2: BiometricSpO2Snapshot | int | None = None
    sleep: BiometricSleepSnapshot | None = None
    activity: BiometricActivitySnapshot | None = None
    stress: BiometricStressSnapshot | None = None
    fatigue: BiometricFatigueSnapshot | None = None

    # Legacy flat fields. Remove after all callers use the nested contract.
    resting_heart_rate: int | None = None
    steps: int | None = None
    calories: int | None = None
    active_minutes: int | None = None
    stress_level: int | None = None
    fatigue_score: int | None = None
    sleep_duration_minutes: int | None = None
    sleep_quality_score: int | None = None
    hrv_ms: int | None = None
    body_temperature: float | None = None
    respiratory_rate: int | None = None

    model_config = ConfigDict(extra="forbid")

    def uses_legacy_flat_contract(self) -> bool:
        flat_fields = (
            "resting_heart_rate",
            "steps",
            "calories",
            "active_minutes",
            "stress_level",
            "fatigue_score",
            "sleep_duration_minutes",
            "sleep_quality_score",
            "hrv_ms",
            "body_temperature",
            "respiratory_rate",
        )
        return (
            isinstance(self.heart_rate, int)
            or isinstance(self.spo2, int)
            or any(getattr(self, field) is not None for field in flat_fields)
        )

    def to_flat_columns(self) -> dict[str, int | float | str | None]:
        heart_rate = self.heart_rate.bpm if isinstance(self.heart_rate, BiometricHeartRateSnapshot) else self.heart_rate
        resting_heart_rate = (
            self.heart_rate.resting_bpm
            if isinstance(self.heart_rate, BiometricHeartRateSnapshot)
            else self.resting_heart_rate
        )
        spo2 = self.spo2.percent if isinstance(self.spo2, BiometricSpO2Snapshot) else self.spo2
        return {
            "provider": self.provider,
            "heart_rate": heart_rate,
            "resting_heart_rate": resting_heart_rate,
            "spo2": spo2,
            "steps": self.activity.steps if self.activity else self.steps,
            "calories": self.activity.calories if self.activity else self.calories,
            "active_minutes": self.activity.active_minutes if self.activity else self.active_minutes,
            "stress_level": self.stress.level if self.stress else self.stress_level,
            "fatigue_score": self.fatigue.score if self.fatigue else self.fatigue_score,
            "sleep_duration_minutes": self.sleep.duration_minutes if self.sleep else self.sleep_duration_minutes,
            "sleep_quality_score": self.sleep.quality_score if self.sleep else self.sleep_quality_score,
            "hrv_ms": self.hrv_ms,
            "body_temperature": self.body_temperature,
            "respiratory_rate": self.respiratory_rate,
        }


# --- Voice Capsule manifest (served to mobile) ---


class VoiceCapsuleTrigger(BaseModel):
    kind: str  # "time" | "pre_event" | "geofence" | "biometric_threshold"
    # time
    at: str | None = None  # "HH:MM" local or ISO absolute
    absolute_ts: int | None = None  # unix seconds
    # pre_event
    event_id: str | None = None
    offset_min: int | None = None
    # geofence
    zone: str | None = None  # place_{id} | "home"
    event: str | None = None  # "enter" | "exit" | "dwell"
    cooldown_min: int | None = None
    # Geofence payload inlined so the phone doesn't have to re-resolve the
    # place — brain-side is the only place that knows the authoritative coords.
    lat: float | None = None
    lon: float | None = None
    radius_m: int | None = None
    # biometric_threshold
    metric: str | None = None  # heart_rate|stress|fatigue|sedentary_minutes
    op: str | None = None  # "gt" | "lt"
    value: float | None = None


class VoiceCapsuleClip(BaseModel):
    id: str
    trigger: VoiceCapsuleTrigger
    audio_url: str
    transcript: str | None = None
    priority: int = 5
    tone: str | None = "neutral"
    expires_at: datetime | None = None
    tags: list[str] = []


class VoiceCapsuleBankClip(BaseModel):
    id: str
    tag: str
    audio_url: str
    transcript: str | None = None


class VoiceCapsuleManifest(BaseModel):
    capsule_id: str  # "2026-04-17"
    character_version: str | None = None
    generated_at: datetime | None = None
    expires_at: datetime | None = None
    clips: list[VoiceCapsuleClip] = []
    generic_bank: list[VoiceCapsuleBankClip] = []


class VoiceCapsulePlayAck(BaseModel):
    capsule_id: str
    clip_id: str
    played_at: datetime
    trigger_drift_sec: int | None = None
    context_json: str | None = None


class VoiceCapsulePlayLogRecord(BaseModel):
    """Listable shape of one VoiceCapsulePlayLog row (admin-only endpoint)."""

    id: int
    capsule_id: int  # FK id (integer) of VoiceCapsule row
    clip_id: str
    played_at: datetime
    trigger_drift_sec: int | None = None
    context_json: str | None = None

    model_config = ConfigDict(from_attributes=True)


# --- Feedback / Learning ---


class AgentFeedbackCreate(BaseModel):
    target_type: str
    target_id: str
    feedback_type: str
    channel: str = "frontend"
    payload: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    user_id: str | None = None


class AgentFeedback(BaseModel):
    id: int
    target_type: str
    target_id: str
    feedback_type: str
    channel: str
    payload: dict
    context: dict
    user_id: str | None = None
    recorded_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentFeedbackStats(BaseModel):
    target_type: str | None = None
    target_id: str | None = None
    total: int = 0
    positive: int = 0
    negative: int = 0
    reruns: int = 0
    cancels: int = 0


class AgentTrajectoryCreate(BaseModel):
    cycle_id: str | None = None
    decision_id: str | None = None
    timestamp: datetime | None = None
    trigger_events: list = Field(default_factory=list)
    tool_calls: list = Field(default_factory=list)
    world_state_snapshot: dict = Field(default_factory=dict)
    outcome_summary: dict = Field(default_factory=dict)


class AgentTrajectory(BaseModel):
    id: int
    cycle_id: str | None = None
    decision_id: str | None = None
    timestamp: datetime | None = None
    trigger_events: list
    tool_calls: list
    world_state_snapshot: dict
    outcome_summary: dict

    model_config = ConfigDict(from_attributes=True)


# --- Adaptive Thresholds ---


class ThresholdDriftLogCreate(BaseModel):
    metric_key: str
    detector: str
    old_value: float | None = None
    proposed_value: float | None = None
    reason: str = "drift"
    status: str = "proposed"
    context_json: dict = Field(default_factory=dict)


class ThresholdDriftLog(BaseModel):
    id: int
    metric_key: str
    detector: str
    detected_at: datetime | None = None
    old_value: float | None = None
    proposed_value: float | None = None
    reason: str | None = None
    status: str
    context_json: dict

    model_config = ConfigDict(from_attributes=True)


class ThresholdAdjustmentCreate(BaseModel):
    metric_key: str
    base_value: float
    offset: float
    approved_by: str = "auto"
    drift_log_id: int | None = None


class ThresholdAdjustment(BaseModel):
    id: int
    metric_key: str
    base_value: float
    offset: float
    applied_at: datetime | None = None
    approved_by: str | None = None
    drift_log_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class ThresholdDecideRequest(BaseModel):
    decision: str  # approve | reject | auto_apply
    reviewer_id: str | None = None
    reason: str | None = None


class ThresholdProposalResponse(BaseModel):
    id: int
    metric_key: str
    detector: str
    detected_at: datetime | None = None
    old_value: float | None = None
    proposed_value: float | None = None
    reason: str | None = None
    status: str
    context_json: dict
