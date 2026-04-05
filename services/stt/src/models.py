"""Pydantic request/response models for STT API."""
from pydantic import BaseModel, Field


class TranscribeResponse(BaseModel):
    text: str = Field(description="Raw transcription")
    cleaned_text: str = Field(description="After query cleaning")
    language: str = Field(default="ja")
    confidence: float = Field(default=0.0)
    duration_seconds: float = Field(default=0.0)
    provider: str = Field(default="whisper")


class ProviderInfo(BaseModel):
    active: str
    available: list[str]
    language: str
    model: str


class HealthResponse(BaseModel):
    status: str
    provider: str
    model: str
    model_loaded: bool
