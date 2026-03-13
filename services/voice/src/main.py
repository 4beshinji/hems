"""HEMS Voice Service — Plugin-based TTS with character awareness."""
import asyncio
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
_health_task: asyncio.Task | None = None
_last_health: dict = {"healthy": True, "state": "starting"}


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


async def _voisona_health_loop():
    """Passive health monitor for VoiSona TTS provider.

    Instead of sending probe synthesis requests ("テスト"), this loop monitors
    the time since last successful synthesis. The brain's AmbientSpeaker sends
    periodic contextual speech that doubles as an implicit health check.
    If no synthesis has succeeded within the threshold, VoiSona is flagged as
    potentially degraded.
    """
    global _last_health
    from providers.voisona import HEALTH_CHECK_INTERVAL, HEALTH_SLOW_THRESHOLD
    STALE_THRESHOLD = HEALTH_CHECK_INTERVAL * 3  # no synthesis for 15min → degraded
    await asyncio.sleep(60)  # initial grace period
    while True:
        try:
            if hasattr(tts_provider, "_last_synth_duration"):
                # Check API reachability
                reachable = await tts_provider.is_available()
                if not reachable:
                    tts_provider._healthy = False
                    _last_health = {
                        "healthy": False, "wall_seconds": 0,
                        "state": "unreachable", "detail": "VoiSona API unreachable",
                    }
                    logger.warning("VoiSona health: API unreachable")
                elif tts_provider._last_synth_duration > HEALTH_SLOW_THRESHOLD:
                    _last_health = {
                        "healthy": True, "wall_seconds": tts_provider._last_synth_duration,
                        "state": "slow", "detail": f"Last synthesis took {tts_provider._last_synth_duration:.1f}s",
                    }
                    logger.info(f"VoiSona health: slow ({tts_provider._last_synth_duration:.1f}s)")
                else:
                    _last_health = {
                        "healthy": tts_provider._healthy,
                        "wall_seconds": tts_provider._last_synth_duration,
                        "state": "ok" if tts_provider._healthy else "degraded",
                        "detail": "",
                    }
                    if tts_provider._healthy:
                        logger.debug(f"VoiSona health OK (last synth {tts_provider._last_synth_duration:.1f}s)")
                    else:
                        logger.warning("VoiSona health: degraded (last synthesis failed)")
        except Exception as e:
            logger.error(f"VoiSona health check error: {e}")
            _last_health = {"healthy": False, "state": "error", "detail": str(e)}
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global character_config, tts_provider, speech_gen, _health_task
    character_config = _load_character()
    tts_provider = create_provider(character_config=character_config)
    speech_gen = SpeechGenerator(character_config=character_config)
    logger.info(f"TTS provider: {tts_provider.name}")
    if tts_provider.name == "voisona":
        _health_task = asyncio.create_task(_voisona_health_loop())
        logger.info("VoiSona health check started (every 5min)")
    yield
    if _health_task:
        _health_task.cancel()


app = FastAPI(title="HEMS Voice Service", lifespan=lifespan)


@app.get("/")
async def root():
    return {"service": "HEMS Voice", "tts": tts_provider.name if tts_provider else "none"}


@app.get("/api/voice/health")
async def health():
    """Detailed health status including VoiSona probe results."""
    base = {"service": "HEMS Voice", "tts": tts_provider.name if tts_provider else "none"}
    if tts_provider and hasattr(tts_provider, "healthy"):
        base["tts_healthy"] = tts_provider.healthy
        base["last_health_check"] = _last_health
    return base



@app.post("/api/voice/synthesize", response_model=VoiceResponse)
async def synthesize_text(req: SynthesizeRequest):
    result = await tts_provider.synthesize(req.text, voice=req.tone or "neutral")
    if not result.audio_data:
        return VoiceResponse(
            text_generated=req.text,
            duration_seconds=result.duration or 0.0,
            played_directly=True,
        )
    fname = f"speak_{uuid.uuid4()}.mp3"
    await _save_audio(result, AUDIO_DIR / fname)
    return VoiceResponse(audio_url=f"/audio/{fname}", text_generated=req.text, duration_seconds=_estimate_duration(result))


@app.post("/api/voice/announce", response_model=VoiceResponse)
async def announce_task(req: TaskAnnounceRequest):
    text = await speech_gen.generate_speech_text(req.task)
    result = await tts_provider.synthesize(text, voice="neutral")
    if not result.audio_data:
        return VoiceResponse(
            text_generated=text,
            duration_seconds=result.duration or 0.0,
            played_directly=True,
        )
    fname = f"task_{uuid.uuid4()}.mp3"
    await _save_audio(result, AUDIO_DIR / fname)
    return VoiceResponse(audio_url=f"/audio/{fname}", text_generated=text, duration_seconds=_estimate_duration(result))


@app.post("/api/voice/announce_with_completion", response_model=DualVoiceResponse)
async def announce_with_completion(req: TaskAnnounceRequest):
    ann_text = await speech_gen.generate_speech_text(req.task)
    comp_text = await speech_gen.generate_completion_text(req.task)
    ann_result = await tts_provider.synthesize(ann_text, voice="neutral")
    comp_result = await tts_provider.synthesize(comp_text, voice="happy")
    direct = not ann_result.audio_data
    if direct:
        return DualVoiceResponse(
            announcement_text=ann_text,
            announcement_duration=ann_result.duration or 0.0,
            completion_text=comp_text,
            completion_duration=comp_result.duration or 0.0,
            played_directly=True,
        )
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
    if not result.audio_data:
        return VoiceResponse(
            text_generated=text,
            duration_seconds=result.duration or 0.0,
            played_directly=True,
        )
    fname = f"fb_{uuid.uuid4()}.mp3"
    await _save_audio(result, AUDIO_DIR / fname)
    return VoiceResponse(audio_url=f"/audio/{fname}", text_generated=text, duration_seconds=_estimate_duration(result))


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    path = AUDIO_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg")
