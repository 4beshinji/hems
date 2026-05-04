"""Pydantic models for HEMS Voice Service API."""

from pydantic import BaseModel


class Task(BaseModel):
    title: str
    description: str | None = None
    location: str | None = None
    urgency: int = 2
    zone: str | None = None
    task_type: list[str] | None = None
    estimated_duration: int | None = 10


class SynthesizeRequest(BaseModel):
    text: str
    tone: str | None = "neutral"


class TaskAnnounceRequest(BaseModel):
    task: Task


class VoiceResponse(BaseModel):
    audio_url: str | None = None
    text_generated: str
    duration_seconds: float = 0.0
    played_directly: bool = False


class DualVoiceResponse(BaseModel):
    announcement_audio_url: str | None = None
    announcement_text: str
    announcement_duration: float = 0.0
    completion_audio_url: str | None = None
    completion_text: str
    completion_duration: float = 0.0
    played_directly: bool = False


class BatchSynthesizeItem(BaseModel):
    clip_id: str  # deterministic; appears in the output filename
    text: str
    tone: str | None = "neutral"


class BatchSynthesizeRequest(BaseModel):
    prefix: str  # e.g. "capsule_2026-04-17" — path-safe
    items: list[BatchSynthesizeItem]


class BatchSynthesizeResult(BaseModel):
    clip_id: str
    audio_url: str | None = None
    duration_seconds: float = 0.0
    error: str | None = None


class BatchSynthesizeResponse(BaseModel):
    results: list[BatchSynthesizeResult]
