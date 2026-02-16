"""HEMS Voice Service — Plugin-based TTS with character awareness."""
import io
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from loguru import logger
from pydub import AudioSegment

from models import SynthesizeRequest, TaskAnnounceRequest, VoiceResponse, DualVoiceResponse
from provider_factory import create_provider
from speech_generator import SpeechGenerator
from tts_provider import AudioResult

AUDIO_DIR = Path("/app/audio")
AUDIO_DIR.mkdir(exist_ok=True)

character_config = {}
tts_provider = None
speech_gen = None


def _load_character() -> dict:
    for path in [os.getenv("CHARACTER_FILE", ""), "/config/character.yaml"]:
        if path and Path(path).exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load character: {e}")
    return {}


def _estimate_duration(result: AudioResult) -> float:
    if result.format == "mp3":
        try:
            seg = AudioSegment.from_mp3(io.BytesIO(result.audio_data))
            return round(seg.duration_seconds, 2)
        except Exception:
            return round(len(result.audio_data) / 2000, 2)
    sr = result.sample_rate or 24000
    return round(len(result.audio_data) / (sr * 2), 2)


async def _save_audio(result: AudioResult, filepath: Path):
    if result.format == "wav":
        seg = AudioSegment.from_wav(io.BytesIO(result.audio_data))
        seg.export(str(filepath), format="mp3", bitrate="64k")
    else:
        filepath.write_bytes(result.audio_data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global character_config, tts_provider, speech_gen
    character_config = _load_character()
    tts_provider = create_provider(character_config=character_config)
    speech_gen = SpeechGenerator(character_config=character_config)
    logger.info(f"TTS provider: {tts_provider.name}")
    yield


app = FastAPI(title="HEMS Voice Service", lifespan=lifespan)


@app.get("/")
async def root():
    return {"service": "HEMS Voice", "tts": tts_provider.name if tts_provider else "none"}


@app.post("/api/voice/synthesize", response_model=VoiceResponse)
async def synthesize_text(req: SynthesizeRequest):
    result = await tts_provider.synthesize(req.text, voice=req.tone or "neutral")
    fname = f"speak_{uuid.uuid4()}.mp3"
    await _save_audio(result, AUDIO_DIR / fname)
    return VoiceResponse(audio_url=f"/audio/{fname}", text_generated=req.text, duration_seconds=_estimate_duration(result))


@app.post("/api/voice/announce", response_model=VoiceResponse)
async def announce_task(req: TaskAnnounceRequest):
    text = await speech_gen.generate_speech_text(req.task)
    result = await tts_provider.synthesize(text, voice="neutral")
    fname = f"task_{uuid.uuid4()}.mp3"
    await _save_audio(result, AUDIO_DIR / fname)
    return VoiceResponse(audio_url=f"/audio/{fname}", text_generated=text, duration_seconds=_estimate_duration(result))


@app.post("/api/voice/announce_with_completion", response_model=DualVoiceResponse)
async def announce_with_completion(req: TaskAnnounceRequest):
    ann_text = await speech_gen.generate_speech_text(req.task)
    comp_text = await speech_gen.generate_completion_text(req.task)
    ann_result = await tts_provider.synthesize(ann_text, voice="neutral")
    comp_result = await tts_provider.synthesize(comp_text, voice="happy")
    ann_fname = f"ann_{uuid.uuid4()}.mp3"
    comp_fname = f"comp_{uuid.uuid4()}.mp3"
    await _save_audio(ann_result, AUDIO_DIR / ann_fname)
    await _save_audio(comp_result, AUDIO_DIR / comp_fname)
    return DualVoiceResponse(
        announcement_audio_url=f"/audio/{ann_fname}", announcement_text=ann_text,
        announcement_duration=_estimate_duration(ann_result),
        completion_audio_url=f"/audio/{comp_fname}", completion_text=comp_text,
        completion_duration=_estimate_duration(comp_result),
    )


@app.post("/api/voice/feedback/{feedback_type}")
async def generate_feedback(feedback_type: str):
    text = await speech_gen.generate_feedback(feedback_type)
    result = await tts_provider.synthesize(text, voice="neutral")
    fname = f"fb_{uuid.uuid4()}.mp3"
    await _save_audio(result, AUDIO_DIR / fname)
    return VoiceResponse(audio_url=f"/audio/{fname}", text_generated=text, duration_seconds=_estimate_duration(result))


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    path = AUDIO_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg")
