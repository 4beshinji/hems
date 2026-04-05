"""
Chat router — conversational AI endpoint.
Persists messages and proxies to Brain chat server for LLM processing.
"""
import asyncio
import io
import json
import os
import re
import struct
import subprocess
import tempfile
import wave
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from database import get_db
import models
import schemas

router = APIRouter(prefix="/chat", tags=["chat"])

BRAIN_CHAT_URL = os.getenv("BRAIN_CHAT_URL", "http://brain:8080")
VOICE_SERVICE_URL = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")
_HEMS_API_KEY = os.getenv("HEMS_API_KEY", "")
_AUTH_HEADERS = {"Authorization": f"Bearer {_HEMS_API_KEY}"} if _HEMS_API_KEY else {}

SLIDING_WINDOW = 20     # max messages sent to brain
TTS_MAX_LENGTH = 100    # auto-synthesize responses shorter than this


@router.post("/", response_model=schemas.ChatResponse)
async def send_message(req: schemas.ChatMessageSend, db: AsyncSession = Depends(get_db)):
    """Send a chat message, get AI response via Brain."""
    content = req.content.strip()
    if not content:
        raise HTTPException(400, "Empty message")

    # 1. Get or create conversation
    if req.conversation_id:
        result = await db.execute(
            select(models.Conversation).where(
                models.Conversation.id == req.conversation_id,
                models.Conversation.is_active == True,
            )
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(404, "Conversation not found")
    else:
        conv = models.Conversation(title=content[:50])
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

    # 2. Store user message
    user_msg = models.Message(
        conversation_id=conv.id,
        role="user",
        content=content,
    )
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)

    # 3. Load conversation history (sliding window)
    result = await db.execute(
        select(models.Message)
        .where(models.Message.conversation_id == conv.id)
        .order_by(models.Message.created_at.desc())
        .limit(SLIDING_WINDOW)
    )
    history_rows = result.scalars().all()
    history = [
        {"role": m.role, "content": m.content}
        for m in reversed(history_rows)  # oldest first
        if m.id != user_msg.id  # exclude current message (sent separately)
    ]

    # 4. Call Brain chat endpoint
    brain_response = await _call_brain(history, content)

    # 5. TTS synthesis: force if tts=True, auto for short responses, skip if tts=False
    audio_url = None
    should_tts = (
        req.tts is True
        or (req.tts is None and len(brain_response["content"]) <= TTS_MAX_LENGTH)
    )
    if should_tts and brain_response["content"]:
        audio_url = await _synthesize_speech(brain_response["content"])

    # 6. Store assistant message
    assistant_msg = models.Message(
        conversation_id=conv.id,
        role="assistant",
        content=brain_response["content"],
        audio_url=audio_url,
        tool_calls_json=json.dumps(brain_response.get("tool_calls", []), ensure_ascii=False)
        if brain_response.get("tool_calls") else None,
    )
    db.add(assistant_msg)

    # Update conversation timestamp
    await db.execute(
        update(models.Conversation)
        .where(models.Conversation.id == conv.id)
        .values(updated_at=user_msg.created_at)
    )
    await db.commit()
    await db.refresh(assistant_msg)

    return schemas.ChatResponse(
        user_message=schemas.ChatMessage.model_validate(user_msg),
        assistant_message=schemas.ChatMessage.model_validate(assistant_msg),
        conversation_id=conv.id,
    )


@router.get("/conversations", response_model=List[schemas.ConversationSummary])
async def list_conversations(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """List recent conversations."""
    limit = min(limit, 50)
    result = await db.execute(
        select(models.Conversation)
        .where(models.Conversation.is_active == True)
        .order_by(models.Conversation.updated_at.desc())
        .limit(limit)
    )
    convs = result.scalars().all()

    items = []
    for c in convs:
        # Get last message for preview
        msg_result = await db.execute(
            select(models.Message.content)
            .where(models.Message.conversation_id == c.id)
            .order_by(models.Message.created_at.desc())
            .limit(1)
        )
        last = msg_result.scalar_one_or_none()
        items.append(schemas.ConversationSummary(
            id=c.id, title=c.title, is_active=c.is_active,
            created_at=c.created_at, updated_at=c.updated_at,
            last_message=last[:100] if last else None,
        ))
    return items


@router.get("/conversations/{conversation_id}", response_model=schemas.ConversationDetail)
async def get_conversation(conversation_id: int, db: AsyncSession = Depends(get_db)):
    """Get conversation with full message history."""
    result = await db.execute(
        select(models.Conversation).where(models.Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversation not found")

    msg_result = await db.execute(
        select(models.Message)
        .where(models.Message.conversation_id == conversation_id)
        .order_by(models.Message.created_at.asc())
    )
    messages = [schemas.ChatMessage.model_validate(m) for m in msg_result.scalars().all()]

    return schemas.ConversationDetail(
        id=conv.id, title=conv.title, is_active=conv.is_active,
        created_at=conv.created_at, updated_at=conv.updated_at,
        messages=messages,
    )


@router.delete("/conversations/{conversation_id}")
async def archive_conversation(conversation_id: int, db: AsyncSession = Depends(get_db)):
    """Archive (soft delete) a conversation."""
    result = await db.execute(
        select(models.Conversation).where(models.Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversation not found")

    conv.is_active = False
    await db.commit()
    return {"success": True}


# --- Internal helpers ---

async def _call_brain(history: list[dict], user_message: str) -> dict:
    """Proxy chat request to Brain HTTP server."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                f"{BRAIN_CHAT_URL}/chat",
                json={"messages": history, "user_message": user_message},
                headers=_AUTH_HEADERS,
            )
            if resp.status_code != 200:
                logger.warning(f"Brain chat error: {resp.status_code} {resp.text[:200]}")
                raise HTTPException(502, "Brain chat request failed")
            return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "Brain chat timeout")
    except httpx.ConnectError:
        raise HTTPException(502, "Brain chat server unreachable")


async def _synthesize_speech(text: str) -> str | None:
    """Synthesize TTS audio. Short text → single call, long text → chunk + pool + concat."""
    if not text.strip():
        return None

    # Short text: single synthesis
    if len(text) <= TTS_MAX_LENGTH:
        return await _synth_single(text)

    # Long text: chunk → parallel synth → concatenate
    try:
        return await _synth_chunked(text)
    except Exception as e:
        logger.warning(f"Chunked TTS failed, falling back to single: {e}")
        # Fallback: truncate and single-synth
        return await _synth_single(text[:300])


async def _synth_single(text: str) -> str | None:
    """Single TTS synthesis call."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(
                f"{VOICE_SERVICE_URL}/api/voice/synthesize",
                json={"text": text, "tone": "neutral"},
                headers=_AUTH_HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("audio_url")
    except Exception as e:
        logger.debug(f"TTS synthesis failed (non-fatal): {e}")
    return None


# --- Chunked TTS ---

_SPLIT_RE = re.compile(r"(?<=[。！？\n])|(?<=\. )|(?<=! )|(?<=\? )")
_COMMA_RE = re.compile(r"(?<=[、，,])")
_MAX_CHUNK = 200


def _split_text(text: str) -> list[str]:
    """Split text into sentence-level chunks (max ~200 chars each)."""
    # Split on sentence boundaries first
    parts = _SPLIT_RE.split(text)
    chunks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= _MAX_CHUNK:
            chunks.append(part)
        else:
            # Split on commas for oversized sentences
            sub = _COMMA_RE.split(part)
            buf = ""
            for s in sub:
                if buf and len(buf) + len(s) > _MAX_CHUNK:
                    chunks.append(buf.strip())
                    buf = ""
                buf += s
            if buf.strip():
                chunks.append(buf.strip())
    return [c for c in chunks if c]


async def _synth_chunk(client: httpx.AsyncClient, text: str, index: int) -> tuple[int, bytes | None]:
    """Synthesize a single chunk, return (index, wav_bytes or None)."""
    try:
        resp = await client.post(
            f"{VOICE_SERVICE_URL}/api/voice/synthesize",
            json={"text": text, "tone": "neutral", "format": "wav"},
            headers=_AUTH_HEADERS,
        )
        if resp.status_code != 200:
            logger.debug(f"Chunk {index} synth failed: {resp.status_code}")
            return (index, None)
        data = resp.json()
        audio_url = data.get("audio_url")
        if not audio_url:
            return (index, None)
        # Fetch the audio file
        audio_resp = await client.get(
            f"{VOICE_SERVICE_URL}{audio_url}" if audio_url.startswith("/") else audio_url,
        )
        if audio_resp.status_code == 200:
            return (index, audio_resp.content)
    except Exception as e:
        logger.debug(f"Chunk {index} synth error: {e}")
    return (index, None)


def _concat_audio(wav_chunks: list[bytes]) -> bytes:
    """Concatenate WAV/MP3 audio chunks into a single MP3 using ffmpeg."""
    if len(wav_chunks) == 1:
        return wav_chunks[0]

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write chunk files
        paths = []
        for i, data in enumerate(wav_chunks):
            path = os.path.join(tmpdir, f"{i:04d}.audio")
            with open(path, "wb") as f:
                f.write(data)
            paths.append(path)

        # Create concat list
        list_path = os.path.join(tmpdir, "concat.txt")
        with open(list_path, "w") as f:
            for p in paths:
                f.write(f"file '{p}'\n")

        out_path = os.path.join(tmpdir, "out.mp3")
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", list_path,
                "-acodec", "libmp3lame", "-q:a", "2",
                out_path,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(f"ffmpeg concat error: {result.stderr.decode()[:200]}")
            return wav_chunks[0]  # fallback to first chunk

        with open(out_path, "rb") as f:
            return f.read()


async def _synth_chunked(text: str) -> str | None:
    """Split text → parallel TTS → concat → save as single audio file."""
    chunks = _split_text(text)
    if not chunks:
        return None
    if len(chunks) == 1:
        return await _synth_single(chunks[0])

    logger.debug(f"Chunked TTS: {len(chunks)} chunks from {len(text)} chars")

    # Parallel synthesis with concurrency limit
    sem = asyncio.Semaphore(3)

    async def limited_synth(client, chunk_text, idx):
        async with sem:
            return await _synth_chunk(client, chunk_text, idx)

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        tasks = [
            limited_synth(client, chunk, i)
            for i, chunk in enumerate(chunks)
        ]
        results = await asyncio.gather(*tasks)

    # Collect in order, skip failures
    ordered = sorted(results, key=lambda r: r[0])
    wav_data = [data for _, data in ordered if data]
    if not wav_data:
        return None

    # Concatenate
    combined = await asyncio.get_event_loop().run_in_executor(
        None, _concat_audio, wav_data
    )

    # Save to voice service audio directory via a temp upload or direct write
    # Since voice service manages audio files, we save via its endpoint
    # Alternative: write directly if we share the volume
    import hashlib
    import time
    filename = f"chat_tts_{int(time.time())}_{hashlib.md5(text[:50].encode()).hexdigest()[:8]}.mp3"

    # Try to write to voice service audio dir (shared volume)
    audio_dir = "/app/audio"
    if os.path.isdir(audio_dir):
        filepath = os.path.join(audio_dir, filename)
        with open(filepath, "wb") as f:
            f.write(combined)
        return f"/audio/{filename}"

    # Fallback: save locally and return via backend
    local_dir = os.path.join(os.getenv("DATA_DIR", "/app/data"), "audio")
    os.makedirs(local_dir, exist_ok=True)
    filepath = os.path.join(local_dir, filename)
    with open(filepath, "wb") as f:
        f.write(combined)
    return f"/audio/{filename}"
