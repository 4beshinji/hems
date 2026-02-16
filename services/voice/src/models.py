"""Pydantic models for HEMS Voice Service API."""
from pydantic import BaseModel
from typing import Optional, List


class Task(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    xp_reward: int = 100
    urgency: int = 2
    zone: Optional[str] = None
    task_type: Optional[List[str]] = None
    estimated_duration: Optional[int] = 10


class SynthesizeRequest(BaseModel):
    text: str
    tone: Optional[str] = "neutral"


class TaskAnnounceRequest(BaseModel):
    task: Task


class VoiceResponse(BaseModel):
    audio_url: str
    text_generated: str
    duration_seconds: float = 0.0


class DualVoiceResponse(BaseModel):
    announcement_audio_url: str
    announcement_text: str
    announcement_duration: float = 0.0
    completion_audio_url: str
    completion_text: str
    completion_duration: float = 0.0
