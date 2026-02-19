from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from database import Base

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    location = Column(String)
    bounty_gold = Column(Integer, default=10)
    bounty_xp = Column(Integer, default=50)
    is_completed = Column(Boolean, default=False)
    
    # Voice announcement fields
    announcement_audio_url = Column(String, nullable=True)
    announcement_text = Column(String, nullable=True)
    completion_audio_url = Column(String, nullable=True)
    completion_text = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    task_type = Column(String, nullable=True) # JSON list of strings
    
    # Intelligent scheduling fields
    urgency = Column(Integer, default=2)  # 0-4 (DEFERRED to CRITICAL)
    zone = Column(String, nullable=True)
    min_people_required = Column(Integer, default=1)
    estimated_duration = Column(Integer, default=10)  # minutes
    is_queued = Column(Boolean, default=False)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    
    # Completion report
    report_status = Column(String, nullable=True)  # no_issue / resolved / needs_followup / cannot_resolve
    completion_note = Column(String, nullable=True)  # Free-text (max 500 chars)

    # Reminder tracking
    last_reminded_at = Column(DateTime(timezone=True), nullable=True)

    # Assignment tracking
    assigned_to = Column(Integer, nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)

class VoiceEvent(Base):
    __tablename__ = "voice_events"
    id = Column(Integer, primary_key=True, index=True)
    message = Column(String)
    audio_url = Column(String)
    zone = Column(String, nullable=True)
    tone = Column(String, default="neutral")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SystemStats(Base):
    __tablename__ = "system_stats"
    id = Column(Integer, primary_key=True, default=1)
    total_xp = Column(Integer, default=0)
    tasks_completed = Column(Integer, default=0)
    tasks_created = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    display_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
