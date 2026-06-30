import uuid

from sqlalchemy import JSON, Boolean, Column, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.sql import func

from database import Base, TZDateTime


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    location = Column(String)
    is_completed = Column(Boolean, default=False)

    # Intelligent scheduling fields
    urgency = Column(Integer, default=2)  # 0-4 (DEFERRED to CRITICAL)
    zone = Column(String, nullable=True)
    estimated_duration = Column(Integer, default=10)  # minutes
    is_queued = Column(Boolean, default=False)
    dispatched_at = Column(TZDateTime(timezone=True), nullable=True)

    # Voice announcement fields
    announcement_audio_url = Column(String, nullable=True)
    announcement_text = Column(String, nullable=True)
    completion_audio_url = Column(String, nullable=True)
    completion_text = Column(String, nullable=True)

    # Timestamps
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())
    completed_at = Column(TZDateTime(timezone=True), nullable=True)
    expires_at = Column(TZDateTime(timezone=True), nullable=True)

    # Classification
    task_type = Column(String, nullable=True)  # JSON list of strings

    # Completion report
    report_status = Column(String, nullable=True)
    completion_note = Column(String, nullable=True)

    # Reminder tracking
    last_reminded_at = Column(TZDateTime(timezone=True), nullable=True)

    # Assignment tracking
    assigned_to = Column(Integer, nullable=True)
    accepted_at = Column(TZDateTime(timezone=True), nullable=True)

    # Timeline / scheduling fields
    cognitive_load = Column(Integer, nullable=True)  # 0=light, 1=medium, 2=focus, 3=deep_focus
    preferred_time_slot = Column(String, nullable=True)  # morning|afternoon|evening|deep_night|anytime
    deadline = Column(TZDateTime(timezone=True), nullable=True)
    source = Column(String, nullable=True)  # user|extractor:pws|extractor:obsidian|prep_auto
    source_ref = Column(String, nullable=True)  # calendar event id, note path, etc.
    confidence = Column(Float, nullable=True)  # LLM extraction confidence 0.0-1.0
    proposal_status = Column(String, nullable=True)  # NULL=active|proposed|dismissed
    dismissed_at = Column(TZDateTime(timezone=True), nullable=True)
    dismiss_reason = Column(String, nullable=True)
    locked_start = Column(TZDateTime(timezone=True), nullable=True)


class ScheduledBlock(Base):
    __tablename__ = "scheduled_blocks"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, nullable=False, index=True)  # YYYY-MM-DD (JST)
    start_ts = Column(TZDateTime(timezone=True), nullable=False)
    end_ts = Column(TZDateTime(timezone=True), nullable=False)
    kind = Column(String, nullable=False)  # calendar|task|routine_wake|commute_out|commute_in|focus_free|sleep|prep
    ref_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    ref_calendar_event_id = Column(String, nullable=True)
    title = Column(String, nullable=False)
    location = Column(String, nullable=True)
    is_locked = Column(Boolean, default=False)
    travel_buffer_minutes = Column(Integer, default=0)
    generated_at = Column(TZDateTime(timezone=True), server_default=func.now())


class DismissLog(Base):
    __tablename__ = "dismiss_log"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    task_title = Column(String, nullable=True)
    task_type_json = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    context_json = Column(String, nullable=True)  # {hour, cognitive_load, source, ...}
    dismissed_at = Column(TZDateTime(timezone=True), server_default=func.now())


class TaskPreference(Base):
    __tablename__ = "task_preferences"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False, index=True)  # e.g., "dismiss:focus:morning"
    count = Column(Integer, default=0)
    last_seen = Column(TZDateTime(timezone=True), server_default=func.now())
    weight = Column(Float, default=0.0)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    display_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())


class VoiceEvent(Base):
    __tablename__ = "voice_events"
    id = Column(Integer, primary_key=True, index=True)
    message = Column(String)
    audio_url = Column(String)
    zone = Column(String, nullable=True)
    tone = Column(String, default="neutral")
    motion_id = Column(String, nullable=True)
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())
    feedback_score = Column(Float, nullable=True)


class TimeSeriesPoint(Base):
    __tablename__ = "timeseries"
    id = Column(Integer, primary_key=True, index=True)
    metric = Column(String, nullable=False, index=True)
    value = Column(Float, nullable=False)
    zone = Column(String, nullable=True, index=True)
    recorded_at = Column(TZDateTime(timezone=True), server_default=func.now(), index=True)


class SystemStats(Base):
    __tablename__ = "system_stats"
    id = Column(Integer, primary_key=True, default=1)
    tasks_completed = Column(Integer, default=0)
    tasks_created = Column(Integer, default=0)
    updated_at = Column(TZDateTime(timezone=True), onupdate=func.now())


class ShoppingItem(Base):
    __tablename__ = "shopping_items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    category = Column(String, nullable=True, index=True)
    quantity = Column(Integer, default=1)
    unit = Column(String, nullable=True)
    store = Column(String, nullable=True)
    store_category = Column(String, nullable=True, index=True)
    price = Column(Integer, nullable=True)
    is_purchased = Column(Boolean, default=False)
    is_recurring = Column(Boolean, default=False)
    recurrence_days = Column(Integer, nullable=True)
    last_purchased_at = Column(TZDateTime(timezone=True), nullable=True)
    next_purchase_at = Column(TZDateTime(timezone=True), nullable=True)
    notes = Column(String, nullable=True)
    priority = Column(Integer, default=1)
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())
    purchased_at = Column(TZDateTime(timezone=True), nullable=True)
    created_by = Column(String, default="user")
    share_token = Column(String, nullable=True, unique=True)


class PurchaseHistory(Base):
    __tablename__ = "purchase_history"
    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String, nullable=False, index=True)
    category = Column(String, nullable=True)
    store = Column(String, nullable=True)
    price = Column(Integer, nullable=True)
    quantity = Column(Integer, default=1)
    purchased_at = Column(TZDateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())
    updated_at = Column(TZDateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(String, nullable=False)
    audio_url = Column(String, nullable=True)
    tool_calls_json = Column(String, nullable=True)
    metadata_json = Column(String, nullable=True)
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())


class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, nullable=False, index=True)  # "tapo.plug_desklight"
    vendor = Column(String, nullable=False, index=True)  # zigbee|switchbot|tapo|ha|mcp|ir_via_hub
    vendor_ref = Column(String, nullable=True)  # IEEE addr / cloud id / IP / entity_id
    kind = Column(String, nullable=False, default="actuator")  # sensor|actuator|both
    device_class = Column(String, nullable=True)  # plug|light|bulb|pump|soil|temp_humidity|co2|pir|hub_ir|curtain
    capabilities = Column(JSON, default=list)  # ["on_off","brightness","color_temp","pulse","ir_send"]
    channels = Column(JSON, default=list)  # sensors: ["temperature","humidity","soil_moisture"]
    units = Column(JSON, default=dict)  # {"temperature":"°C"}
    display_name = Column(String, nullable=True)
    zone = Column(String, nullable=True, index=True)
    location = Column(String, nullable=True)
    purpose = Column(String, nullable=True)  # LLM context: "起床補助ライト"
    description = Column(String, nullable=True)
    model_id = Column(String, nullable=True)  # Z2M definition.model e.g. "LED2109G6"
    manufacturer = Column(String, nullable=True)  # Z2M definition.vendor e.g. "IKEA"
    icon = Column(String, nullable=True)  # lucide icon name
    last_state = Column(JSON, default=dict)  # {"on":true,"brightness":200}
    last_value = Column(JSON, default=dict)  # {"temperature":22.5,"humidity":55}
    last_seen = Column(TZDateTime(timezone=True), nullable=True)  # wall-clock receipt time
    last_seen_reported = Column(TZDateTime(timezone=True), nullable=True)  # device-reported timestamp (Z2M last_seen)
    battery_pct = Column(Integer, nullable=True)
    link_quality = Column(Integer, nullable=True)  # Z2M LQI (0-255), Switchbot RSSI
    is_enabled = Column(Boolean, default=True)
    notes = Column(String, nullable=True)
    metadata_json = Column(String, nullable=True)  # vendor固有設定JSON
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())
    updated_at = Column(TZDateTime(timezone=True), onupdate=func.now())


class Scene(Base):
    __tablename__ = "scenes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)  # programmatic id "wake_up"
    display_name = Column(String, nullable=False)  # "起床シーン"
    description = Column(String, nullable=True)
    actions = Column(JSON, nullable=False, default=list)
    # [{"device_id":str,"action":str,"params":dict,"delay_s":int}]
    is_enabled = Column(Boolean, default=True)
    last_executed_at = Column(TZDateTime(timezone=True), nullable=True)
    execution_count = Column(Integer, default=0)
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())
    updated_at = Column(TZDateTime(timezone=True), onupdate=func.now())


class AutomationRule(Base):
    __tablename__ = "automation_rules"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    enabled = Column(Boolean, default=True)
    trigger_type = Column(String, nullable=False, index=True)
    # sensor_threshold|schedule|event|device_state
    trigger_config = Column(JSON, nullable=False, default=dict)
    actions = Column(JSON, nullable=False, default=list)  # scene action format
    cooldown_s = Column(Integer, default=600)
    last_fired_at = Column(TZDateTime(timezone=True), nullable=True)
    mode = Column(String, default="direct")  # direct|llm_review
    require_confirm = Column(Boolean, default=False)
    risk_tier = Column(String, nullable=True, default="low")  # safe|low|medium|high|critical
    reversibility = Column(String, nullable=True, default="reversible")  # reversible|compensatable|irreversible
    approval_required = Column(Boolean, default=False)
    auto_rollback_window_seconds = Column(Integer, nullable=True, default=300)
    fire_count = Column(Integer, default=0)
    last_evaluation_ts = Column(Float, nullable=True)  # for sustain_s tracking
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())
    updated_at = Column(TZDateTime(timezone=True), onupdate=func.now())


class BiometricReading(Base):
    __tablename__ = "biometric_readings"
    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False, index=True)
    heart_rate = Column(Integer, nullable=True)
    resting_heart_rate = Column(Integer, nullable=True)
    spo2 = Column(Integer, nullable=True)
    steps = Column(Integer, nullable=True)
    calories = Column(Integer, nullable=True)
    active_minutes = Column(Integer, nullable=True)
    stress_level = Column(Integer, nullable=True)
    fatigue_score = Column(Integer, nullable=True)
    sleep_duration_minutes = Column(Integer, nullable=True)
    sleep_quality_score = Column(Integer, nullable=True)
    hrv_ms = Column(Integer, nullable=True)
    body_temperature = Column(Float, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)
    recorded_at = Column(TZDateTime(timezone=True), server_default=func.now(), index=True)


class FrequentPlace(Base):
    __tablename__ = "frequent_places"
    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    radius_m = Column(Integer, default=200)
    enabled = Column(Boolean, default=True)
    cooldown_min = Column(Integer, default=60)
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())
    updated_at = Column(TZDateTime(timezone=True), onupdate=func.now())


class ClassifierCache(Base):
    __tablename__ = "classifier_cache"
    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, nullable=False, index=True)
    key_hash = Column(String, nullable=False, index=True)
    value_json = Column(String, nullable=False)
    source = Column(String, nullable=False)
    hit_count = Column(Integer, default=1)
    learned_at = Column(TZDateTime(timezone=True), server_default=func.now())
    updated_at = Column(TZDateTime(timezone=True), onupdate=func.now())
    __table_args__ = (UniqueConstraint("kind", "key_hash", name="uq_classifier_kind_key"),)


class MobileDevice(Base):
    __tablename__ = "mobile_devices"
    id = Column(Integer, primary_key=True, index=True)
    device_label = Column(String, nullable=False)
    api_key_hash = Column(String, nullable=False, unique=True, index=True)
    hmac_secret = Column(String, nullable=False)
    platform = Column(String, nullable=True)
    registered_at = Column(TZDateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(TZDateTime(timezone=True), nullable=True)
    enabled = Column(Boolean, default=True)


class VoiceCapsule(Base):
    __tablename__ = "voice_capsules"
    id = Column(Integer, primary_key=True, index=True)
    capsule_date = Column(String, nullable=False, index=True)
    character_version = Column(String, nullable=True)
    manifest_json = Column(Text, nullable=False)
    generated_at = Column(TZDateTime(timezone=True), server_default=func.now())
    expires_at = Column(TZDateTime(timezone=True), nullable=True)
    invalidated = Column(Boolean, default=False)


class VoiceCapsulePlayLog(Base):
    __tablename__ = "voice_capsule_play_log"
    id = Column(Integer, primary_key=True, index=True)
    capsule_id = Column(Integer, ForeignKey("voice_capsules.id"), index=True)
    clip_id = Column(String, nullable=False)
    played_at = Column(TZDateTime(timezone=True), server_default=func.now())
    trigger_drift_sec = Column(Integer, nullable=True)
    context_json = Column(Text, nullable=True)


class BridgeStatusLog(Base):
    """Per-bridge connection state transitions for SLA / uptime tracking."""

    __tablename__ = "bridge_status_log"
    id = Column(Integer, primary_key=True, index=True)
    service = Column(String, nullable=False, index=True)  # weather, news, biometric, ...
    state = Column(String, nullable=False)  # connected | disconnected
    timestamp = Column(TZDateTime(timezone=True), server_default=func.now(), index=True)
    detail = Column(String, nullable=True)  # optional reason / error


class DeviceActionLog(Base):
    """Device state transitions / control actions for 24h timeline view."""

    __tablename__ = "device_action_log"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)  # on | off | toggle | set_brightness | ...
    params = Column(JSON, nullable=True, default=dict)
    source = Column(String, nullable=True)  # llm | rule | scene | api | ...
    success = Column(Boolean, default=True)
    timestamp = Column(TZDateTime(timezone=True), server_default=func.now(), index=True)
    feedback_score = Column(Float, nullable=True)


class Approval(Base):
    """Human-in-the-loop approval request and audit trail."""

    __tablename__ = "approvals"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(String, nullable=True, index=True)
    rule_id = Column(Integer, ForeignKey("automation_rules.id"), nullable=True, index=True)
    action_type = Column(String, nullable=False)  # device_control|scene|rule_promotion|config_change
    risk_tier = Column(String, nullable=False, default="low")  # safe|low|medium|high|critical
    reversibility = Column(String, nullable=False, default="reversible")  # reversible|compensatable|irreversible
    confidence = Column(Float, nullable=True)
    proposed_payload = Column(JSON, nullable=False, default=dict)
    context = Column(JSON, nullable=False, default=dict)
    status = Column(
        String, nullable=False, default="proposed", index=True
    )  # proposed|pending|approved|rejected|modified|expired|rolled_back
    reviewer_id = Column(String, nullable=True)
    decision = Column(String, nullable=True)  # approve|reject|modify
    decision_reason = Column(String, nullable=True)
    requested_at = Column(TZDateTime(timezone=True), server_default=func.now())
    decided_at = Column(TZDateTime(timezone=True), nullable=True)
    expires_at = Column(TZDateTime(timezone=True), nullable=True)
    executed_at = Column(TZDateTime(timezone=True), nullable=True)
    rollback_plan = Column(JSON, nullable=True)
    rollback_status = Column(String, nullable=True, default="none")  # none|pending|success|failed
    audit_log = Column(JSON, nullable=False, default=list)


class ActionSnapshot(Base):
    """Pre/post state snapshots for actions subject to approval/rollback."""

    __tablename__ = "action_snapshots"
    id = Column(Integer, primary_key=True)
    approval_id = Column(Uuid(as_uuid=True), ForeignKey("approvals.id"), nullable=False, index=True)
    entity_type = Column(String, nullable=False)  # device|scene|rule|config
    entity_id = Column(String, nullable=False)
    before_state = Column(JSON, nullable=False, default=dict)
    after_state = Column(JSON, nullable=True)
    captured_at = Column(TZDateTime(timezone=True), server_default=func.now())


class RollbackLog(Base):
    """Record of rollback/compensation executions."""

    __tablename__ = "rollback_log"
    id = Column(Integer, primary_key=True)
    approval_id = Column(Uuid(as_uuid=True), ForeignKey("approvals.id"), nullable=False, index=True)
    trigger = Column(String, nullable=False)  # human_reject|verification_failure|timeout|policy_violation
    compensation_plan = Column(JSON, nullable=True)
    execution_status = Column(String, nullable=True)  # pending|success|failed
    started_at = Column(TZDateTime(timezone=True), server_default=func.now())
    completed_at = Column(TZDateTime(timezone=True), nullable=True)
    error_message = Column(String, nullable=True)


class AgentFeedback(Base):
    """Explicit and implicit human feedback on agent actions."""

    __tablename__ = "agent_feedback"
    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String, nullable=False, index=True)
    # task|voice|device_action|approval|scene|rule
    target_id = Column(String, nullable=False, index=True)
    feedback_type = Column(String, nullable=False, index=True)
    # explicit_up | explicit_down | cancel | rerun | snooze | dismiss | complete | implicit_override
    channel = Column(String, nullable=False, default="frontend")  # frontend|voice|mqtt|implicit
    payload = Column(JSON, nullable=False, default=dict)
    context = Column(JSON, nullable=False, default=dict)
    user_id = Column(String, nullable=True, index=True)
    recorded_at = Column(TZDateTime(timezone=True), server_default=func.now(), index=True)


class AgentTrajectory(Base):
    """Decision-to-outcome trajectory used for learning and personalization."""

    __tablename__ = "agent_trajectories"
    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(String, nullable=True, index=True)
    decision_id = Column(String, nullable=True, index=True)
    timestamp = Column(TZDateTime(timezone=True), server_default=func.now(), index=True)
    trigger_events = Column(JSON, nullable=False, default=list)
    tool_calls = Column(JSON, nullable=False, default=list)
    world_state_snapshot = Column(JSON, nullable=False, default=dict)
    outcome_summary = Column(JSON, nullable=False, default=dict)
