"""Pydantic models for HEMS Voice Service API."""
from pydantic import BaseModel
from typing import Optional, List


class Task(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
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
    audio_url: Optional[str] = None
    text_generated: str
    duration_seconds: float = 0.0
    played_directly: bool = False


class DualVoiceResponse(BaseModel):
    announcement_audio_url: Optional[str] = None
    announcement_text: str
    announcement_duration: float = 0.0
    completion_audio_url: Optional[str] = None
    completion_text: str
    completion_duration: float = 0.0
    played_directly: bool = False


class BatchSynthesizeItem(BaseModel):
    clip_id: str                # deterministic; appears in the output filename
    text: str
    tone: Optional[str] = "neutral"


class BatchSynthesizeRequest(BaseModel):
    prefix: str                 # e.g. "capsule_2026-04-17" — path-safe
    items: List[BatchSynthesizeItem]


class BatchSynthesizeResult(BaseModel):
    clip_id: str
    audio_url: Optional[str] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None


class BatchSynthesizeResponse(BaseModel):
    results: List[BatchSynthesizeResult]
