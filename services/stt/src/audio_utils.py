"""Audio format conversion utilities."""
import io
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from loguru import logger

TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1


def convert_to_wav(audio_data: bytes, original_filename: str = "") -> bytes:
    """Convert audio data to 16kHz mono WAV. Handles WebM/Opus, MP3, WAV, etc."""
    ext = Path(original_filename).suffix.lower() if original_filename else ""

    # Try direct read with soundfile first (handles WAV, FLAC, OGG)
    if ext in (".wav", ".flac", ".ogg", ""):
        try:
            return _normalize_with_soundfile(audio_data)
        except Exception:
            pass

    # Fallback: use ffmpeg for WebM/Opus, MP3, etc.
    return _convert_with_ffmpeg(audio_data)


def _normalize_with_soundfile(audio_data: bytes) -> bytes:
    """Read and normalize audio with soundfile."""
    data, sr = sf.read(io.BytesIO(audio_data), dtype="float32")

    # Convert to mono if stereo
    if data.ndim > 1:
        data = data.mean(axis=1)

    # Resample if needed
    if sr != TARGET_SAMPLE_RATE:
        data = _resample(data, sr, TARGET_SAMPLE_RATE)

    buf = io.BytesIO()
    sf.write(buf, data, TARGET_SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _convert_with_ffmpeg(audio_data: bytes) -> bytes:
    """Convert any audio format to 16kHz mono WAV via ffmpeg."""
    with tempfile.NamedTemporaryFile(suffix=".input", delete=True) as tmp_in:
        tmp_in.write(audio_data)
        tmp_in.flush()

        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", tmp_in.name,
                    "-ar", str(TARGET_SAMPLE_RATE),
                    "-ac", str(TARGET_CHANNELS),
                    "-f", "wav",
                    "-acodec", "pcm_s16le",
                    "pipe:1",
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.error(f"ffmpeg error: {result.stderr.decode()[:200]}")
                raise RuntimeError("ffmpeg conversion failed")
            return result.stdout
        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found")


def _resample(data: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Simple linear interpolation resampling."""
    if orig_sr == target_sr:
        return data
    ratio = target_sr / orig_sr
    new_length = int(len(data) * ratio)
    indices = np.linspace(0, len(data) - 1, new_length)
    return np.interp(indices, np.arange(len(data)), data).astype(np.float32)


def get_audio_duration(audio_data: bytes) -> float:
    """Get duration in seconds from WAV data."""
    try:
        data, sr = sf.read(io.BytesIO(audio_data), dtype="float32")
        return len(data) / sr
    except Exception:
        return 0.0
