"""
HEMS STT Service — Plugin-based Speech-to-Text with query cleaning.
"""
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from loguru import logger

from audio_utils import convert_to_wav, get_audio_duration
from models import HealthResponse, ProviderInfo, TranscribeResponse
from provider_factory import create_provider, get_available_providers
from query_cleaner import QueryCleaner
from stt_provider import STTProvider

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
HEMS_API_KEY = os.getenv("HEMS_API_KEY", "")
MAX_AUDIO_SECONDS = int(os.getenv("STT_MAX_AUDIO_SECONDS", "60"))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB

logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    level=LOG_LEVEL,
    format="{time:HH:mm:ss} | {level:<7} | {message}",
)

provider: STTProvider | None = None
cleaner: QueryCleaner | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global provider, cleaner

    logger.info("STT Service starting...")
    provider = create_provider()
    cleaner = QueryCleaner()

    available = get_available_providers()
    logger.info(
        f"Provider: {provider.name} ({provider.model_name}), "
        f"available: {available}"
    )

    yield

    if cleaner:
        await cleaner.close()
    logger.info("STT Service stopped")


app = FastAPI(title="HEMS STT Service", lifespan=lifespan)


def _check_auth(authorization: str | None):
    if not HEMS_API_KEY:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.removeprefix("Bearer ").strip()
    if token != HEMS_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
async def health() -> HealthResponse:
    avail = await provider.is_available() if provider else False
    return HealthResponse(
        status="ok" if avail else "degraded",
        provider=provider.name if provider else "none",
        model=provider.model_name if provider else "none",
        model_loaded=avail,
    )


@app.get("/api/stt/providers")
async def get_providers(
    authorization: str | None = Header(None),
) -> ProviderInfo:
    _check_auth(authorization)
    return ProviderInfo(
        active=provider.name if provider else "none",
        available=get_available_providers(),
        language=os.getenv("STT_LANGUAGE", "ja"),
        model=provider.model_name if provider else "none",
    )


@app.post("/api/stt/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: str = Form("ja"),
    clean: bool = Form(True),
    authorization: str | None = Header(None),
) -> TranscribeResponse:
    _check_auth(authorization)

    if not provider:
        raise HTTPException(status_code=503, detail="STT provider not loaded")

    # Read and validate upload
    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 10MB)")
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio file too small")

    # Convert to normalized WAV
    t0 = time.monotonic()
    try:
        wav_data = convert_to_wav(audio_bytes, audio.filename or "")
    except Exception as e:
        logger.error(f"Audio conversion failed: {e}")
        raise HTTPException(status_code=400, detail=f"Audio conversion failed: {e}")

    # Check duration
    duration = get_audio_duration(wav_data)
    if duration > MAX_AUDIO_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"Audio too long ({duration:.0f}s > {MAX_AUDIO_SECONDS}s)",
        )

    # Transcribe
    try:
        result = await provider.transcribe(wav_data, language)
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    elapsed = time.monotonic() - t0
    logger.info(
        f"Transcribed {duration:.1f}s audio in {elapsed:.2f}s "
        f"({provider.name}): {result.text[:60]}"
    )

    # Query cleaning
    cleaned_text = result.text
    if clean and cleaner and result.text:
        cleaned_text = await cleaner.clean(result.text, result.language)
        if cleaned_text != result.text:
            logger.debug(f"Cleaned: '{result.text}' -> '{cleaned_text}'")

    return TranscribeResponse(
        text=result.text,
        cleaned_text=cleaned_text,
        language=result.language,
        confidence=result.confidence,
        duration_seconds=result.duration_seconds,
        provider=provider.name,
    )
