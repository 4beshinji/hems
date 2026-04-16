from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime


# --- Task ---

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    expires_at: Optional[datetime] = None
    task_type: Optional[List[str]] = None
    urgency: int = 2
    zone: Optional[str] = None
    estimated_duration: int = 10
    announcement_audio_url: Optional[str] = None
    announcement_text: Optional[str] = None
    completion_audio_url: Optional[str] = None
    completion_text: Optional[str] = None
    cognitive_load: Optional[int] = None
    preferred_time_slot: Optional[str] = None
    deadline: Optional[datetime] = None
    source: Optional[str] = None
    source_ref: Optional[str] = None
    confidence: Optional[float] = None
    proposal_status: Optional[str] = None


class Task(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    is_completed: bool = False
    is_queued: bool = False
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    task_type: Optional[List[str]] = None
    urgency: int = 2
    zone: Optional[str] = None
    estimated_duration: int = 10
    announcement_audio_url: Optional[str] = None
    announcement_text: Optional[str] = None
    completion_audio_url: Optional[str] = None
    completion_text: Optional[str] = None
    assigned_to: Optional[int] = None
    accepted_at: Optional[datetime] = None
    last_reminded_at: Optional[datetime] = None
    report_status: Optional[str] = None
    completion_note: Optional[str] = None
    cognitive_load: Optional[int] = None
    preferred_time_slot: Optional[str] = None
    deadline: Optional[datetime] = None
    source: Optional[str] = None
    source_ref: Optional[str] = None
    confidence: Optional[float] = None
    proposal_status: Optional[str] = None
    dismissed_at: Optional[datetime] = None
    dismiss_reason: Optional[str] = None
    locked_start: Optional[datetime] = None

    class Config:
        from_attributes = True


class TaskComplete(BaseModel):
    report_status: Optional[str] = None
    completion_note: Optional[str] = None


class TaskAccept(BaseModel):
    user_id: Optional[int] = None


class TaskDismiss(BaseModel):
    reason: Optional[str] = None


class TaskLock(BaseModel):
    locked_start: datetime


# --- Timeline ---

class ScheduledBlock(BaseModel):
    id: int
    date: str
    start_ts: datetime
    end_ts: datetime
    kind: str
    ref_task_id: Optional[int] = None
    ref_calendar_event_id: Optional[str] = None
    title: str
    location: Optional[str] = None
    is_locked: bool = False
    travel_buffer_minutes: int = 0
    generated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScheduledBlockIn(BaseModel):
    start_ts: datetime
    end_ts: datetime
    kind: str
    ref_task_id: Optional[int] = None
    ref_calendar_event_id: Optional[str] = None
    title: str
    location: Optional[str] = None
    is_locked: bool = False
    travel_buffer_minutes: int = 0


class TimelineRegenerate(BaseModel):
    date: str
    blocks: List[ScheduledBlockIn]


class TimelineResponse(BaseModel):
    date: str
    blocks: List[ScheduledBlock]
    generated_at: Optional[datetime] = None


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
    zone: Optional[str] = None
    tone: str = "neutral"
    motion_id: Optional[str] = None


class VoiceEvent(BaseModel):
    id: int
    message: str
    audio_url: str
    zone: Optional[str] = None
    tone: str = "neutral"
    motion_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- User ---

class UserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None


class UserUpdate(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None


class User(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Zone / Sensor ---

class EnvironmentData(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    co2: Optional[float] = None
    pressure: Optional[float] = None
    light: Optional[float] = None
    voc: Optional[float] = None
    last_update: Optional[float] = None


class OccupancyData(BaseModel):
    count: int = 0
    last_update: Optional[float] = None


class ZoneSnapshot(BaseModel):
    zone_id: str
    environment: EnvironmentData = EnvironmentData()
    occupancy: OccupancyData = OccupancyData()
    events: List[dict] = []


class ZonesUpdate(BaseModel):
    zones: List[ZoneSnapshot]


# --- Shopping List ---

class ShoppingItemCreate(BaseModel):
    name: str
    category: Optional[str] = None
    quantity: int = 1
    unit: Optional[str] = None
    store: Optional[str] = None
    store_category: Optional[str] = None
    price: Optional[int] = None
    is_recurring: bool = False
    recurrence_days: Optional[int] = None
    notes: Optional[str] = None
    priority: int = 1
    created_by: str = "user"


class ShoppingItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[int] = None
    unit: Optional[str] = None
    store: Optional[str] = None
    store_category: Optional[str] = None
    price: Optional[int] = None
    is_recurring: Optional[bool] = None
    recurrence_days: Optional[int] = None
    notes: Optional[str] = None
    priority: Optional[int] = None


class ShoppingItemPatch(BaseModel):
    """Partial update — only fields explicitly provided are written."""
    name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[int] = None
    unit: Optional[str] = None
    store: Optional[str] = None
    store_category: Optional[str] = None
    price: Optional[int] = None
    is_recurring: Optional[bool] = None
    recurrence_days: Optional[int] = None
    notes: Optional[str] = None
    priority: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


class ShoppingItem(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    quantity: int = 1
    unit: Optional[str] = None
    store: Optional[str] = None
    store_category: Optional[str] = None
    price: Optional[int] = None
    is_purchased: bool = False
    is_recurring: bool = False
    recurrence_days: Optional[int] = None
    last_purchased_at: Optional[datetime] = None
    next_purchase_at: Optional[datetime] = None
    notes: Optional[str] = None
    priority: int = 1
    created_at: Optional[datetime] = None
    purchased_at: Optional[datetime] = None
    created_by: str = "user"
    share_token: Optional[str] = None

    class Config:
        from_attributes = True


class PurchaseHistory(BaseModel):
    id: int
    item_name: str
    category: Optional[str] = None
    store: Optional[str] = None
    price: Optional[int] = None
    quantity: int = 1
    purchased_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ShoppingStats(BaseModel):
    total_items: int = 0
    purchased_items: int = 0
    pending_items: int = 0
    total_spent_this_month: int = 0
    category_breakdown: dict = {}


class ShoppingShareResponse(BaseModel):
    share_url: str
    token: str
    items: List[ShoppingItem] = []


# --- Chat ---

class ChatMessageSend(BaseModel):
    content: str
    conversation_id: Optional[int] = None
    tts: Optional[bool] = None  # None=auto (short responses), True=force, False=skip


class ChatMessage(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    audio_url: Optional[str] = None
    tool_calls_json: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    user_message: ChatMessage
    assistant_message: ChatMessage
    conversation_id: int


class ConversationSummary(BaseModel):
    id: int
    title: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_message: Optional[str] = None

    class Config:
        from_attributes = True


# --- Device Registry ---

class DeviceBase(BaseModel):
    device_id: str
    vendor: str
    vendor_ref: Optional[str] = None
    kind: str = "actuator"  # sensor|actuator|both
    device_class: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    channels: List[str] = Field(default_factory=list)
    units: dict = Field(default_factory=dict)
    display_name: Optional[str] = None
    zone: Optional[str] = None
    location: Optional[str] = None
    purpose: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    battery_pct: Optional[int] = None
    is_enabled: bool = True
    notes: Optional[str] = None
    metadata_json: Optional[str] = None


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    # All fields optional for partial update — metadata editing from UI
    vendor_ref: Optional[str] = None
    kind: Optional[str] = None
    device_class: Optional[str] = None
    capabilities: Optional[List[str]] = None
    channels: Optional[List[str]] = None
    units: Optional[dict] = None
    display_name: Optional[str] = None
    zone: Optional[str] = None
    location: Optional[str] = None
    purpose: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    is_enabled: Optional[bool] = None
    notes: Optional[str] = None
    metadata_json: Optional[str] = None


class Device(DeviceBase):
    id: int
    last_state: dict = Field(default_factory=dict)
    last_value: dict = Field(default_factory=dict)
    last_seen: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DeviceHeartbeat(BaseModel):
    """Brain push: create-or-update on sensor/actuator activity."""
    device_id: str
    vendor: str
    vendor_ref: Optional[str] = None
    kind: Optional[str] = None
    device_class: Optional[str] = None
    capabilities: Optional[List[str]] = None
    channels: Optional[List[str]] = None
    units: Optional[dict] = None
    zone: Optional[str] = None
    last_state: Optional[dict] = None
    last_value: Optional[dict] = None
    battery_pct: Optional[int] = None


class DeviceControlRequest(BaseModel):
    """UI manual control: forwarded via Brain to the physical device."""
    action: str  # on|off|toggle|set_brightness|set_color_temp|set_position|pulse|ir_send
    params: dict = Field(default_factory=dict)


class DeviceControlResponse(BaseModel):
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None


class ZigbeePermitJoinRequest(BaseModel):
    """Open/close the Z2M coordinator for new device pairing."""
    enable: bool
    duration_s: int = Field(default=60, ge=0, le=3600,
                            description="Auto-close after N seconds (0 = open until closed)")


# --- Scene ---

class SceneAction(BaseModel):
    device_id: str
    action: str
    params: dict = Field(default_factory=dict)
    delay_s: int = 0


class SceneBase(BaseModel):
    name: str  # programmatic ID "wake_up"
    display_name: str
    description: Optional[str] = None
    actions: List[SceneAction] = Field(default_factory=list)
    is_enabled: bool = True


class SceneCreate(SceneBase):
    pass


class SceneUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    actions: Optional[List[SceneAction]] = None
    is_enabled: Optional[bool] = None


class Scene(SceneBase):
    id: int
    last_executed_at: Optional[datetime] = None
    execution_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SceneExecuteResponse(BaseModel):
    success: bool
    executed: int
    errors: List[str] = Field(default_factory=list)


# --- AutomationRule ---

class AutomationRuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    trigger_type: str  # sensor_threshold|schedule|event|device_state
    trigger_config: dict = Field(default_factory=dict)
    actions: List[SceneAction] = Field(default_factory=list)
    cooldown_s: int = 600
    mode: str = "direct"  # direct|llm_review
    require_confirm: bool = False


class AutomationRuleCreate(AutomationRuleBase):
    pass


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[dict] = None
    actions: Optional[List[SceneAction]] = None
    cooldown_s: Optional[int] = None
    mode: Optional[str] = None
    require_confirm: Optional[bool] = None


class AutomationRule(AutomationRuleBase):
    id: int
    last_fired_at: Optional[datetime] = None
    fire_count: int = 0
    last_evaluation_ts: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AutomationRuleFireUpdate(BaseModel):
    """Brain → backend: record successful firing stats."""
    last_fired_at: datetime
    fire_count: int
    last_evaluation_ts: Optional[float] = None


class ConversationDetail(BaseModel):
    id: int
    title: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    messages: List[ChatMessage] = []

    class Config:
        from_attributes = True


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
    label: Optional[str] = None
    category: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    radius_m: Optional[int] = None
    enabled: Optional[bool] = None
    cooldown_min: Optional[int] = None


class FrequentPlace(BaseModel):
    id: int
    label: str
    category: str
    lat: float
    lon: float
    radius_m: int = 200
    enabled: bool = True
    cooldown_min: int = 60
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


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
    learned_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, extra="ignore")


# --- Mobile device registration & webhook ---

class MobileDeviceRegisterRequest(BaseModel):
    device_label: str
    platform: Optional[str] = None  # "android" | "ios"


class MobileDeviceRegisterResponse(BaseModel):
    device_id: int
    device_key: str        # issued; client stores securely
    hmac_secret: str       # for state webhook signing
    backend_url: Optional[str] = None
    character_version: Optional[str] = None


class MobileDevice(BaseModel):
    id: int
    device_label: str
    platform: Optional[str] = None
    registered_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    enabled: bool = True

    class Config:
        from_attributes = True


class MobileLocationReading(BaseModel):
    lat: float
    lon: float
    accuracy_m: Optional[float] = None
    speed_mps: Optional[float] = None
    heading_deg: Optional[float] = None
    provider: Optional[str] = None  # "fused" | "gps" | "network"


class MobileActivityReading(BaseModel):
    kind: str  # "still" | "walking" | "running" | "in_vehicle" | "on_bicycle" | "unknown"
    confidence: Optional[int] = None


class MobileBiometricReading(BaseModel):
    heart_rate: Optional[int] = None
    spo2: Optional[int] = None
    steps: Optional[int] = None
    stress_level: Optional[int] = None
    sleep_duration_minutes: Optional[int] = None


class MobileStateWebhookPayload(BaseModel):
    ts: datetime  # client-provided timestamp
    location: Optional[MobileLocationReading] = None
    activity: Optional[MobileActivityReading] = None
    biometrics: Optional[MobileBiometricReading] = None
    battery_pct: Optional[int] = None
    app_foreground: Optional[bool] = None


class MobileStateWebhookResponse(BaseModel):
    received: bool = True
    published_topics: List[str] = []


# --- Voice Capsule manifest (served to mobile) ---

class VoiceCapsuleTrigger(BaseModel):
    kind: str  # "time" | "pre_event" | "geofence" | "biometric_threshold"
    # time
    at: Optional[str] = None  # "HH:MM" local or ISO absolute
    absolute_ts: Optional[int] = None  # unix seconds
    # pre_event
    event_id: Optional[str] = None
    offset_min: Optional[int] = None
    # geofence
    zone: Optional[str] = None  # place_{id} | "home"
    event: Optional[str] = None  # "enter" | "exit" | "dwell"
    cooldown_min: Optional[int] = None
    # Geofence payload inlined so the phone doesn't have to re-resolve the
    # place — brain-side is the only place that knows the authoritative coords.
    lat: Optional[float] = None
    lon: Optional[float] = None
    radius_m: Optional[int] = None
    # biometric_threshold
    metric: Optional[str] = None  # heart_rate|stress|fatigue|sedentary_minutes
    op: Optional[str] = None  # "gt" | "lt"
    value: Optional[float] = None


class VoiceCapsuleClip(BaseModel):
    id: str
    trigger: VoiceCapsuleTrigger
    audio_url: str
    transcript: Optional[str] = None
    priority: int = 5
    tone: Optional[str] = "neutral"
    expires_at: Optional[datetime] = None
    tags: List[str] = []


class VoiceCapsuleBankClip(BaseModel):
    id: str
    tag: str
    audio_url: str
    transcript: Optional[str] = None


class VoiceCapsuleManifest(BaseModel):
    capsule_id: str  # "2026-04-17"
    character_version: Optional[str] = None
    generated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    clips: List[VoiceCapsuleClip] = []
    generic_bank: List[VoiceCapsuleBankClip] = []


class VoiceCapsulePlayAck(BaseModel):
    capsule_id: str
    clip_id: str
    played_at: datetime
    trigger_drift_sec: Optional[int] = None
    context_json: Optional[str] = None


class VoiceCapsulePlayLogRecord(BaseModel):
    """Listable shape of one VoiceCapsulePlayLog row (admin-only endpoint)."""
    id: int
    capsule_id: int  # FK id (integer) of VoiceCapsule row
    clip_id: str
    played_at: datetime
    trigger_drift_sec: Optional[int] = None
    context_json: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
