"""HEMS Voice Service — Plugin-based TTS with character awareness."""

import asyncio
import hmac
import io
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from loguru import logger
from provider_factory import create_provider
from pydub import AudioSegment
from speech_generator import SpeechGenerator
from text_processor import TextProcessor
from tts_provider import AudioResult

from models import (
    BatchSynthesizeItem,
    BatchSynthesizeRequest,
    BatchSynthesizeResponse,
    BatchSynthesizeResult,
    DualVoiceResponse,
    SynthesizeRequest,
    TaskAnnounceRequest,
    VoiceResponse,
)

AUDIO_DIR = Path("/app/audio")
AUDIO_DIR.mkdir(exist_ok=True)
_INTERNAL_TOKEN = os.getenv("HEMS_INTERNAL_TOKEN", "")

character_config = {}
tts_provider = None
speech_gen = None
text_processor = TextProcessor()
_health_task: asyncio.Task | None = None
_last_health: dict = {"healthy": True, "state": "starting"}


def _load_character() -> dict:
    for path in [os.getenv("CHARACTER_FILE", ""), "/config/character.yaml"]:
        if path and Path(path).exists():
            try:
                with open(path, encoding="utf-8") as f:
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


def _get_voisona_provider(provider):
    """Extract VoisonaProvider from a provider (possibly wrapped in FallbackProvider)."""
    from providers.voisona import VoisonaProvider

    if isinstance(provider, VoisonaProvider):
        return provider
    if hasattr(provider, "primary") and isinstance(provider.primary, VoisonaProvider):
        return provider.primary
    return None


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

    _stale_threshold = HEALTH_CHECK_INTERVAL * 3  # no synthesis for 15min → degraded
    await asyncio.sleep(60)  # initial grace period
    while True:
        try:
            voisona = _get_voisona_provider(tts_provider)
            if voisona and hasattr(voisona, "_last_synth_duration"):
                # Check API reachability
                reachable = await voisona.is_available()
                if not reachable:
                    voisona._healthy = False
                    _last_health = {
                        "healthy": False,
                        "wall_seconds": 0,
                        "state": "unreachable",
                        "detail": "VoiSona API unreachable",
                    }
                    logger.warning("VoiSona health: API unreachable")
                elif voisona._last_synth_duration > HEALTH_SLOW_THRESHOLD:
                    _last_health = {
                        "healthy": True,
                        "wall_seconds": voisona._last_synth_duration,
                        "state": "slow",
                        "detail": f"Last synthesis took {voisona._last_synth_duration:.1f}s",
                    }
                    logger.info(f"VoiSona health: slow ({voisona._last_synth_duration:.1f}s)")
                else:
                    _last_health = {
                        "healthy": voisona._healthy,
                        "wall_seconds": voisona._last_synth_duration,
                        "state": "ok" if voisona._healthy else "degraded",
                        "detail": "",
                    }
                    if voisona._healthy:
                        logger.debug(f"VoiSona health OK (last synth {voisona._last_synth_duration:.1f}s)")
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
    # Start VoiSona health loop if primary provider is voisona (including fallback wrapper)
    _voisona = _get_voisona_provider(tts_provider)
    if _voisona:
        _health_task = asyncio.create_task(_voisona_health_loop())
        logger.info("VoiSona health check started (every 5min)")
    yield
    if _health_task:
        _health_task.cancel()


app = FastAPI(title="HEMS Voice Service", lifespan=lifespan)


def _check_auth(authorization: str | None):
    if not _INTERNAL_TOKEN:
        return
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, _INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/")
async def root():
    return {"service": "HEMS Voice", "tts": tts_provider.name if tts_provider else "none"}


@app.get("/api/voice/health")
async def health():
    """Detailed health status including VoiSona probe results."""
    base = {"service": "HEMS Voice", "tts": tts_provider.name if tts_provider else "none"}
    voisona = _get_voisona_provider(tts_provider) if tts_provider else None
    if voisona:
        base["tts_healthy"] = voisona.healthy
        base["last_health_check"] = _last_health
    if tts_provider and hasattr(tts_provider, "_using_fallback"):
        base["using_fallback"] = tts_provider._using_fallback
    return base


@app.post("/api/voice/synthesize", response_model=VoiceResponse)
async def synthesize_text(req: SynthesizeRequest, authorization: str | None = Header(None)):
    _check_auth(authorization)
    processed_text = text_processor.process(req.text)
    result = await tts_provider.synthesize(processed_text, voice=req.tone or "neutral")
    if not result.audio_data:
        return VoiceResponse(
            text_generated=req.text,
            duration_seconds=result.duration or 0.0,
            played_directly=True,
        )
    fname = f"speak_{uuid.uuid4()}.mp3"
    await _save_audio(result, AUDIO_DIR / fname)
    return VoiceResponse(
        audio_url=f"/audio/{fname}", text_generated=req.text, duration_seconds=_estimate_duration(result)
    )


@app.post("/api/voice/announce", response_model=VoiceResponse)
async def announce_task(req: TaskAnnounceRequest, authorization: str | None = Header(None)):
    _check_auth(authorization)
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
async def announce_with_completion(req: TaskAnnounceRequest, authorization: str | None = Header(None)):
    _check_auth(authorization)
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
        announcement_audio_url=f"/audio/{ann_fname}",
        announcement_text=ann_text,
        announcement_duration=_estimate_duration(ann_result),
        completion_audio_url=f"/audio/{comp_fname}",
        completion_text=comp_text,
        completion_duration=_estimate_duration(comp_result),
    )


@app.post("/api/voice/feedback/{feedback_type}")
async def generate_feedback(feedback_type: str, authorization: str | None = Header(None)):
    _check_auth(authorization)
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


_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


async def _synth_batch_item(item: BatchSynthesizeItem, prefix: str) -> BatchSynthesizeResult:
    if not _SAFE_NAME_RE.match(item.clip_id):
        return BatchSynthesizeResult(
            clip_id=item.clip_id,
            error="Invalid clip_id (expected [A-Za-z0-9._-]+)",
        )
    try:
        processed = text_processor.process(item.text)
        result = await tts_provider.synthesize(processed, voice=item.tone or "neutral")
        if not result.audio_data:
            return BatchSynthesizeResult(
                clip_id=item.clip_id,
                duration_seconds=result.duration or 0.0,
                error="Provider returned no audio (played directly)",
            )
        fname = f"{prefix}_{item.clip_id}.mp3"
        await _save_audio(result, AUDIO_DIR / fname)
        return BatchSynthesizeResult(
            clip_id=item.clip_id,
            audio_url=f"/audio/{fname}",
            duration_seconds=_estimate_duration(result),
        )
    except Exception as exc:
        logger.warning("batch-synth failed clip_id={} err={}", item.clip_id, exc)
        return BatchSynthesizeResult(clip_id=item.clip_id, error=str(exc)[:200])


@app.post("/api/voice/batch-synthesize", response_model=BatchSynthesizeResponse)
async def batch_synthesize(req: BatchSynthesizeRequest, authorization: str | None = Header(None)):
    _check_auth(authorization)
    """Parallel synthesize a batch of clips with deterministic filenames.

    Output filename is ``{prefix}_{clip_id}.mp3`` — re-running with the same
    prefix overwrites, letting boot-load re-generate a capsule cheaply.
    """
    if not _SAFE_NAME_RE.match(req.prefix):
        raise HTTPException(status_code=400, detail="Invalid prefix")
    if not req.items:
        return BatchSynthesizeResponse(results=[])

    results = await asyncio.gather(
        *(_synth_batch_item(item, req.prefix) for item in req.items),
        return_exceptions=False,
    )
    return BatchSynthesizeResponse(results=list(results))


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    path = (AUDIO_DIR / filename).resolve()
    if not str(path).startswith(str(AUDIO_DIR.resolve()) + "/"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg")
