from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Task Schemas
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    bounty_gold: int = 10
    bounty_xp: int = 50
    expires_at: Optional[datetime] = None
    task_type: Optional[List[str]] = None
    
    # Intelligent scheduling fields
    urgency: int = 2  # 0-4 (DEFERRED to CRITICAL)
    zone: Optional[str] = None
    min_people_required: int = 1
    estimated_duration: int = 10  # minutes
    
    # Voice data (optional, provided by Brain if voice enabled)
    announcement_audio_url: Optional[str] = None
    announcement_text: Optional[str] = None
    completion_audio_url: Optional[str] = None
    completion_text: Optional[str] = None

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    bounty_gold: Optional[int] = None
    is_completed: Optional[bool] = None
    expires_at: Optional[datetime] = None
    task_type: Optional[List[str]] = None
    urgency: Optional[int] = None
    zone: Optional[str] = None
    is_queued: Optional[bool] = None

class Task(TaskBase):
    id: int
    is_completed: bool
    is_queued: bool = False
    created_at: datetime
    completed_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    
    # Voice announcement fields
    announcement_audio_url: Optional[str] = None
    announcement_text: Optional[str] = None
    completion_audio_url: Optional[str] = None
    completion_text: Optional[str] = None
    assigned_to: Optional[int] = None
    accepted_at: Optional[datetime] = None
    last_reminded_at: Optional[datetime] = None
    report_status: Optional[str] = None
    completion_note: Optional[str] = None

    class Config:
        from_attributes = True


class TaskComplete(BaseModel):
    report_status: Optional[str] = None  # no_issue / resolved / needs_followup / cannot_resolve
    completion_note: Optional[str] = None  # Free-text (max 500 chars)

class TaskAccept(BaseModel):
    user_id: Optional[int] = None

# SystemStats Schemas
class SystemStatsResponse(BaseModel):
    total_xp: int = 0
    tasks_completed: int = 0
    tasks_created: int = 0
    tasks_active: int = 0
    tasks_queued: int = 0
    tasks_completed_last_hour: int = 0

# VoiceEvent Schemas
class VoiceEventCreate(BaseModel):
    message: str
    audio_url: str
    zone: Optional[str] = None
    tone: str = "neutral"

class VoiceEvent(VoiceEventCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# User Schemas
class UserBase(BaseModel):
    username: str
    display_name: Optional[str] = None

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None

class User(UserBase):
    id: int
    is_active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True
