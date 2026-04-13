from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from database import Base


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
    dispatched_at = Column(DateTime(timezone=True), nullable=True)

    # Voice announcement fields
    announcement_audio_url = Column(String, nullable=True)
    announcement_text = Column(String, nullable=True)
    completion_audio_url = Column(String, nullable=True)
    completion_text = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Classification
    task_type = Column(String, nullable=True)  # JSON list of strings

    # Completion report
    report_status = Column(String, nullable=True)
    completion_note = Column(String, nullable=True)

    # Reminder tracking
    last_reminded_at = Column(DateTime(timezone=True), nullable=True)

    # Assignment tracking
    assigned_to = Column(Integer, nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)

    # Timeline / scheduling fields
    cognitive_load = Column(Integer, nullable=True)  # 0=light, 1=medium, 2=focus, 3=deep_focus
    preferred_time_slot = Column(String, nullable=True)  # morning|afternoon|evening|deep_night|anytime
    deadline = Column(DateTime(timezone=True), nullable=True)
    source = Column(String, nullable=True)  # user|extractor:pws|extractor:obsidian|prep_auto
    source_ref = Column(String, nullable=True)  # calendar event id, note path, etc.
    confidence = Column(Float, nullable=True)  # LLM extraction confidence 0.0-1.0
    proposal_status = Column(String, nullable=True)  # NULL=active|proposed|dismissed
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    dismiss_reason = Column(String, nullable=True)
    locked_start = Column(DateTime(timezone=True), nullable=True)


class ScheduledBlock(Base):
    __tablename__ = "scheduled_blocks"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, nullable=False, index=True)  # YYYY-MM-DD (JST)
    start_ts = Column(DateTime(timezone=True), nullable=False)
    end_ts = Column(DateTime(timezone=True), nullable=False)
    kind = Column(String, nullable=False)  # calendar|task|routine_wake|commute_out|commute_in|focus_free|sleep|prep
    ref_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    ref_calendar_event_id = Column(String, nullable=True)
    title = Column(String, nullable=False)
    location = Column(String, nullable=True)
    is_locked = Column(Boolean, default=False)
    travel_buffer_minutes = Column(Integer, default=0)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())


class DismissLog(Base):
    __tablename__ = "dismiss_log"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    task_title = Column(String, nullable=True)
    task_type_json = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    context_json = Column(String, nullable=True)  # {hour, cognitive_load, source, ...}
    dismissed_at = Column(DateTime(timezone=True), server_default=func.now())


class TaskPreference(Base):
    __tablename__ = "task_preferences"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False, index=True)  # e.g., "dismiss:focus:morning"
    count = Column(Integer, default=0)
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    weight = Column(Float, default=0.0)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    display_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class VoiceEvent(Base):
    __tablename__ = "voice_events"
    id = Column(Integer, primary_key=True, index=True)
    message = Column(String)
    audio_url = Column(String)
    zone = Column(String, nullable=True)
    tone = Column(String, default="neutral")
    motion_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TimeSeriesPoint(Base):
    __tablename__ = "timeseries"
    id = Column(Integer, primary_key=True, index=True)
    metric = Column(String, nullable=False, index=True)
    value = Column(Float, nullable=False)
    zone = Column(String, nullable=True, index=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class SystemStats(Base):
    __tablename__ = "system_stats"
    id = Column(Integer, primary_key=True, default=1)
    tasks_completed = Column(Integer, default=0)
    tasks_created = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ShoppingItem(Base):
    __tablename__ = "shopping_items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    category = Column(String, nullable=True, index=True)
    quantity = Column(Integer, default=1)
    unit = Column(String, nullable=True)
    store = Column(String, nullable=True)
    price = Column(Integer, nullable=True)
    is_purchased = Column(Boolean, default=False)
    is_recurring = Column(Boolean, default=False)
    recurrence_days = Column(Integer, nullable=True)
    last_purchased_at = Column(DateTime(timezone=True), nullable=True)
    next_purchase_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(String, nullable=True)
    priority = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    purchased_at = Column(DateTime(timezone=True), nullable=True)
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
    purchased_at = Column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String, nullable=False)          # "user" | "assistant"
    content = Column(String, nullable=False)
    audio_url = Column(String, nullable=True)
    tool_calls_json = Column(String, nullable=True)
    metadata_json = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
