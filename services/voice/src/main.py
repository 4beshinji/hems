from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import uuid
from loguru import logger

from models import TaskAnnounceRequest, SynthesizeRequest, VoiceResponse, DualVoiceResponse
from voicevox_client import VoicevoxClient
from speech_generator import SpeechGenerator
from rejection_stock import RejectionStock, idle_generation_loop
from currency_unit_stock import CurrencyUnitStock, idle_currency_generation_loop

# Initialize clients
voice_client = VoicevoxClient()
speech_gen = SpeechGenerator()

# Currency unit stock (text-only, injected into speech_gen)
currency_unit_stock = CurrencyUnitStock(speech_gen)
speech_gen.currency_stock = currency_unit_stock

# Rejection voice stock
rejection_stock = RejectionStock(speech_gen, voice_client)

# Audio storage directory
AUDIO_DIR = Path("/app/audio")
AUDIO_DIR.mkdir(exist_ok=True)

# VOICEVOX output format constants
VOICEVOX_SAMPLE_RATE = 24000
VOICEVOX_BYTES_PER_SAMPLE = 2


def estimate_audio_duration(audio_data: bytes) -> float:
    """Estimate audio duration in seconds from raw PCM data."""
    return round(len(audio_data) / (VOICEVOX_SAMPLE_RATE * VOICEVOX_BYTES_PER_SAMPLE), 2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start idle generation background tasks
    rejection_task = asyncio.create_task(idle_generation_loop(rejection_stock))
    currency_task = asyncio.create_task(idle_currency_generation_loop(currency_unit_stock))
    logger.info("Background idle generation tasks started (rejection + currency)")
    yield
    rejection_task.cancel()
    currency_task.cancel()
    for t in [rejection_task, currency_task]:
        try:
            await t
        except asyncio.CancelledError:
            pass


# Initialize FastAPI app
app = FastAPI(
    title="SOMS Voice Service",
    description="Voice notification service using VOICEVOX and LLM",
    lifespan=lifespan,
)

@app.get("/")
async def root():
    """Basic health check endpoint."""
    return {"service": "SOMS Voice Service", "status": "running"}


@app.get("/health")
async def health():
    """Detailed health check: VOICEVOX + LLM connectivity."""
    import aiohttp

    checks = {}

    # VOICEVOX check
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(f"{voice_client.base_url}/speakers") as resp:
                checks["voicevox"] = "ok" if resp.status == 200 else f"status={resp.status}"
    except Exception as e:
        checks["voicevox"] = f"error: {e}"

    # LLM check
    try:
        llm_url = speech_gen.llm_api_url.rstrip("/")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(f"{llm_url}/models") as resp:
                checks["llm"] = "ok" if resp.status == 200 else f"status={resp.status}"
    except Exception as e:
        checks["llm"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={"status": "healthy" if all_ok else "degraded", "checks": checks},
        status_code=status_code,
    )

@app.post("/api/voice/synthesize", response_model=VoiceResponse)
async def synthesize_text(request: SynthesizeRequest):
    """
    Synthesize text directly to speech (skips LLM text generation).
    Used by the speak tool where the Brain LLM has already generated the message.
    """
    rejection_stock.request_started()
    currency_unit_stock.request_started()
    try:
        logger.info(f"Synthesizing text: {request.text[:50]}...")

        # 1. Synthesize using VOICEVOX
        audio_data = await voice_client.synthesize(request.text)

        # 2. Save audio file
        audio_id = str(uuid.uuid4())
        audio_filename = f"speak_{audio_id}.mp3"
        audio_path = AUDIO_DIR / audio_filename
        await voice_client.save_audio(audio_data, audio_path)

        # 3. Calculate duration
        duration_seconds = estimate_audio_duration(audio_data)

        return VoiceResponse(
            audio_url=f"/audio/{audio_filename}",
            text_generated=request.text,
            duration_seconds=duration_seconds
        )

    except Exception as e:
        logger.error(f"Failed to synthesize text: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rejection_stock.request_finished()
        currency_unit_stock.request_finished()

@app.post("/api/voice/announce", response_model=VoiceResponse)
async def announce_task(request: TaskAnnounceRequest):
    """
    Generate voice announcement for a task.
    
    Flow:
    1. Generate natural speech text using LLM
    2. Synthesize using VOICEVOX (ナースロボ＿タイプＴ)
    3. Save audio file
    4. Return audio URL and metadata
    """
    rejection_stock.request_started()
    currency_unit_stock.request_started()
    try:
        logger.info(f"Announcing task: {request.task.title}")

        # 1. Generate natural speech text using LLM
        speech_text = await speech_gen.generate_speech_text(request.task)

        # 2. Synthesize using VOICEVOX
        audio_data = await voice_client.synthesize(speech_text)

        # 3. Save audio file
        audio_id = str(uuid.uuid4())
        audio_filename = f"task_{audio_id}.mp3"
        audio_path = AUDIO_DIR / audio_filename
        await voice_client.save_audio(audio_data, audio_path)

        # 4. Calculate duration
        duration_seconds = estimate_audio_duration(audio_data)

        return VoiceResponse(
            audio_url=f"/audio/{audio_filename}",
            text_generated=speech_text,
            duration_seconds=duration_seconds
        )

    except Exception as e:
        logger.error(f"Failed to announce task: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rejection_stock.request_finished()
        currency_unit_stock.request_finished()

@app.post("/api/voice/feedback/{feedback_type}")
async def generate_feedback(feedback_type: str):
    """
    Generate feedback message (e.g., task completion acknowledgment).

    Args:
        feedback_type: Type of feedback ('task_completed', 'task_accepted')
    """
    rejection_stock.request_started()
    currency_unit_stock.request_started()
    try:
        logger.info(f"Generating feedback: {feedback_type}")

        # 1. Generate feedback text using LLM
        feedback_text = await speech_gen.generate_feedback(feedback_type)

        # 2. Synthesize
        audio_data = await voice_client.synthesize(feedback_text)

        # 3. Save
        audio_id = str(uuid.uuid4())
        audio_filename = f"feedback_{audio_id}.mp3"
        audio_path = AUDIO_DIR / audio_filename
        await voice_client.save_audio(audio_data, audio_path)

        # 4. Calculate duration
        duration_seconds = estimate_audio_duration(audio_data)

        return VoiceResponse(
            audio_url=f"/audio/{audio_filename}",
            text_generated=feedback_text,
            duration_seconds=duration_seconds
        )

    except Exception as e:
        logger.error(f"Failed to generate feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rejection_stock.request_finished()
        currency_unit_stock.request_finished()

@app.post("/api/voice/announce_with_completion", response_model=DualVoiceResponse)
async def announce_task_with_completion(request: TaskAnnounceRequest):
    """
    Generate both announcement and completion voices for a task.
    The completion voice is contextually linked to the task content.

    Flow:
    1. Generate announcement text using LLM
    2. Generate contextual completion text using LLM
    3. Synthesize both using VOICEVOX
    4. Save both audio files
    5. Return both audio URLs and metadata
    """
    rejection_stock.request_started()
    currency_unit_stock.request_started()
    try:
        logger.info(f"Generating dual voice for task: {request.task.title}")

        # 1. Generate announcement text using LLM
        announcement_text = await speech_gen.generate_speech_text(request.task)

        # 2. Generate contextual completion text using LLM
        completion_text = await speech_gen.generate_completion_text(request.task)

        # 3. Synthesize announcement
        announcement_audio = await voice_client.synthesize(announcement_text)

        # 4. Synthesize completion (with speaker variation)
        completion_speaker = VoicevoxClient.pick_speaker("completion")
        completion_audio = await voice_client.synthesize(completion_text, speaker_id=completion_speaker)

        # 5. Save announcement audio
        announcement_id = str(uuid.uuid4())
        announcement_filename = f"task_announce_{announcement_id}.mp3"
        announcement_path = AUDIO_DIR / announcement_filename
        await voice_client.save_audio(announcement_audio, announcement_path)

        # 6. Save completion audio
        completion_id = str(uuid.uuid4())
        completion_filename = f"task_complete_{completion_id}.mp3"
        completion_path = AUDIO_DIR / completion_filename
        await voice_client.save_audio(completion_audio, completion_path)

        # 7. Calculate durations
        announcement_duration = estimate_audio_duration(announcement_audio)
        completion_duration = estimate_audio_duration(completion_audio)

        logger.info(f"Announcement: {announcement_text}")
        logger.info(f"Completion: {completion_text}")

        return DualVoiceResponse(
            announcement_audio_url=f"/audio/{announcement_filename}",
            announcement_text=announcement_text,
            announcement_duration=announcement_duration,
            completion_audio_url=f"/audio/{completion_filename}",
            completion_text=completion_text,
            completion_duration=completion_duration
        )

    except Exception as e:
        logger.error(f"Failed to generate dual voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rejection_stock.request_finished()
        currency_unit_stock.request_finished()

@app.get("/api/voice/rejection/random")
async def get_random_rejection():
    """
    Get a random pre-generated rejection voice from stock.
    Returns instantly (no synthesis latency) if stock is available.
    Falls back to on-demand synthesis if stock is empty.
    """
    entry = await rejection_stock.get_random()
    if entry:
        return entry

    # Fallback: generate on-demand (slower, but avoids silence)
    logger.warning("Rejection stock empty, generating on-demand")
    rejection_stock.request_started()
    currency_unit_stock.request_started()
    try:
        text = await speech_gen.generate_rejection_text()
        rejection_speaker = VoicevoxClient.pick_speaker("rejection")
        audio_data = await voice_client.synthesize(text, speaker_id=rejection_speaker)
        audio_id = str(uuid.uuid4())[:8]
        audio_filename = f"rejection_ondemand_{audio_id}.mp3"
        audio_path = AUDIO_DIR / audio_filename
        await voice_client.save_audio(audio_data, audio_path)
        return {"audio_url": f"/audio/{audio_filename}", "text": text}
    except Exception as e:
        logger.error(f"On-demand rejection generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rejection_stock.request_finished()
        currency_unit_stock.request_finished()


@app.get("/api/voice/rejection/status")
async def get_rejection_status():
    """Get current rejection voice stock status."""
    return {
        "stock_count": rejection_stock.count,
        "max_stock": 100,
        "is_generating": not rejection_stock.is_idle,
        "needs_refill": rejection_stock.needs_refill,
    }


@app.post("/api/voice/rejection/clear")
async def clear_rejection_stock():
    """Clear all pre-generated rejection stock and force regeneration."""
    await rejection_stock.clear_all()
    return {"status": "cleared", "stock_count": rejection_stock.count}


@app.get("/api/voice/currency-units/status")
async def get_currency_unit_status():
    """Get current currency unit stock status."""
    return {
        "stock_count": currency_unit_stock.count,
        "max_stock": 50,
        "needs_refill": currency_unit_stock.needs_refill,
        "sample": currency_unit_stock.get_random(),
    }


@app.post("/api/voice/currency-units/clear")
async def clear_currency_unit_stock():
    """Clear all pre-generated currency unit stock and force regeneration."""
    await currency_unit_stock.clear_all()
    return {"status": "cleared", "stock_count": currency_unit_stock.count}


@app.get("/audio/rejections/{filename}")
async def serve_rejection_audio(filename: str):
    """Serve pre-generated rejection audio files."""
    from rejection_stock import STOCK_DIR
    audio_path = STOCK_DIR / filename

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")

    return FileResponse(audio_path, media_type="audio/mpeg")


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve generated audio files."""
    audio_path = AUDIO_DIR / filename

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")

    # We omit the filename argument to default to inline disposition,
    # which is better for web playback in <audio> or Audio objects.
    return FileResponse(
        audio_path,
        media_type="audio/mpeg"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
