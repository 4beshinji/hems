from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# --- Task ---

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    xp_reward: int = Field(default=100, ge=50, le=500)
    expires_at: Optional[datetime] = None
    task_type: Optional[List[str]] = None
    urgency: int = 2
    zone: Optional[str] = None
    estimated_duration: int = 10
    announcement_audio_url: Optional[str] = None
    announcement_text: Optional[str] = None
    completion_audio_url: Optional[str] = None
    completion_text: Optional[str] = None


class Task(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    xp_reward: int = 100
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

    class Config:
        from_attributes = True


class TaskComplete(BaseModel):
    report_status: Optional[str] = None
    completion_note: Optional[str] = None


class TaskAccept(BaseModel):
    user_id: Optional[int] = None


# --- SystemStats ---

class SystemStatsResponse(BaseModel):
    total_xp: int = 0
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


class VoiceEvent(BaseModel):
    id: int
    message: str
    audio_url: str
    zone: Optional[str] = None
    tone: str = "neutral"
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
    points: int = 0
    is_active: bool = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- PointLog ---

class PointLogCreate(BaseModel):
    amount: int
    reason: str
    task_id: Optional[int] = None


class PointLog(BaseModel):
    id: int
    user_id: int
    amount: int
    reason: str
    task_id: Optional[int] = None
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
