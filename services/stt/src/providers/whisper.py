"""
Whisper STT provider.
Auto-selects backend based on GPU:
  - NVIDIA (CUDA): faster-whisper (CTranslate2) — optimal
  - AMD (ROCm): transformers + PyTorch ROCm — full GPU acceleration
  - CPU: faster-whisper int8 — still fast enough for real-time
"""
import asyncio
import io
import os
from typing import Protocol

import numpy as np
import soundfile as sf
from loguru import logger

from stt_provider import STTProvider, TranscriptionResult

_DEFAULT_MODEL = "large-v3-turbo"
# HuggingFace model ID for transformers backend
_HF_MODEL_MAP = {
    "large-v3-turbo": "openai/whisper-large-v3-turbo",
    "large-v3": "openai/whisper-large-v3",
    "medium": "openai/whisper-medium",
    "small": "openai/whisper-small",
    "base": "openai/whisper-base",
    "tiny": "openai/whisper-tiny",
}


class _Backend(Protocol):
    def transcribe(
        self, audio: np.ndarray, sr: int, language: str, beam_size: int
    ) -> TranscriptionResult: ...


def _detect_backend(device: str) -> str:
    """Detect optimal backend: 'faster-whisper' or 'transformers'."""
    if device == "rocm":
        return "transformers"

    if device == "auto":
        # Check ROCm first (AMD GPU)
        try:
            import torch

            if torch.cuda.is_available() and hasattr(torch, "hip"):
                logger.info("ROCm detected → using transformers backend")
                return "transformers"
            if hasattr(torch.version, "hip") and torch.version.hip is not None:
                logger.info("ROCm (HIP) detected → using transformers backend")
                return "transformers"
        except ImportError:
            pass

        # Check if /dev/kfd exists (ROCm device)
        if os.path.exists("/dev/kfd"):
            logger.info("/dev/kfd detected → using transformers backend for ROCm")
            return "transformers"

    # CUDA or CPU → faster-whisper (CTranslate2)
    try:
        import faster_whisper  # noqa: F401

        return "faster-whisper"
    except ImportError:
        return "transformers"


class _FasterWhisperBackend:
    """CTranslate2 backend — CUDA and CPU."""

    def __init__(self, model_id: str, device: str, compute_type: str) -> None:
        from faster_whisper import WhisperModel

        # faster-whisper only supports 'cpu' or 'cuda'
        fw_device = "cpu" if device in ("rocm", "auto") else device
        if fw_device == "auto":
            fw_device = "cuda"  # let it try
            try:
                import ctranslate2

                if not ctranslate2.get_cuda_device_count():
                    fw_device = "cpu"
            except Exception:
                fw_device = "cpu"

        if fw_device == "cpu" and compute_type == "auto":
            compute_type = "int8"

        logger.info(
            f"Loading faster-whisper: {model_id} "
            f"(device={fw_device}, compute={compute_type})"
        )
        self._model = WhisperModel(
            model_id,
            device=fw_device,
            compute_type=compute_type,
            download_root=os.getenv("STT_MODEL_DIR", "/app/models"),
        )
        logger.info("faster-whisper model loaded")

    def transcribe(
        self, audio: np.ndarray, sr: int, language: str, beam_size: int
    ) -> TranscriptionResult:
        lang_arg = None if language == "auto" else language
        segments_gen, info = self._model.transcribe(
            audio,
            language=lang_arg,
            beam_size=beam_size,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        segments = []
        texts = []
        for seg in segments_gen:
            texts.append(seg.text)
            segments.append({"start": seg.start, "end": seg.end, "text": seg.text})

        return TranscriptionResult(
            text="".join(texts).strip(),
            language=info.language or language,
            confidence=info.language_probability or 0.0,
            duration_seconds=info.duration or 0.0,
            segments=segments,
        )


class _TransformersBackend:
    """PyTorch backend — ROCm and CUDA. Also works on CPU as fallback."""

    def __init__(self, model_id: str, device: str, compute_type: str) -> None:
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        hf_model = _HF_MODEL_MAP.get(model_id, model_id)

        # Resolve device
        if device in ("auto", "rocm"):
            if torch.cuda.is_available():
                self._device = "cuda:0"
            else:
                self._device = "cpu"
        elif device == "cuda":
            self._device = "cuda:0"
        else:
            self._device = "cpu"

        # Resolve dtype
        if compute_type in ("float16", "auto") and "cuda" in self._device:
            self._dtype = torch.float16
        else:
            self._dtype = torch.float32

        logger.info(
            f"Loading transformers Whisper: {hf_model} "
            f"(device={self._device}, dtype={self._dtype})"
        )
        cache_dir = os.getenv("STT_MODEL_DIR", "/app/models")
        self._processor = AutoProcessor.from_pretrained(
            hf_model, cache_dir=cache_dir
        )
        self._model = AutoModelForSpeechSeq2Seq.from_pretrained(
            hf_model,
            torch_dtype=self._dtype,
            cache_dir=cache_dir,
        ).to(self._device)
        self._model.eval()
        logger.info(f"transformers Whisper loaded on {self._device}")

    def transcribe(
        self, audio: np.ndarray, sr: int, language: str, beam_size: int
    ) -> TranscriptionResult:
        import torch

        inputs = self._processor(
            audio, sampling_rate=sr, return_tensors="pt"
        )
        input_features = inputs.input_features.to(
            device=self._device, dtype=self._dtype
        )

        gen_kwargs: dict = {"max_new_tokens": 448}
        if beam_size > 1:
            gen_kwargs["num_beams"] = beam_size
        if language and language != "auto":
            gen_kwargs["language"] = language
            gen_kwargs["task"] = "transcribe"

        with torch.no_grad():
            predicted_ids = self._model.generate(
                input_features, **gen_kwargs
            )

        text = self._processor.batch_decode(
            predicted_ids, skip_special_tokens=True
        )[0].strip()

        duration = len(audio) / sr if sr > 0 else 0.0

        return TranscriptionResult(
            text=text,
            language=language if language != "auto" else "ja",
            confidence=0.9 if text else 0.0,
            duration_seconds=duration,
        )


class WhisperProvider(STTProvider):
    def __init__(self) -> None:
        self._model_id = os.getenv("STT_MODEL", _DEFAULT_MODEL)
        self._device = os.getenv("STT_DEVICE", "auto")
        self._compute_type = os.getenv("STT_COMPUTE_TYPE", "auto")
        self._beam_size = int(os.getenv("STT_BEAM_SIZE", "5"))
        self._backend: _Backend | None = None
        self._backend_name = ""
        self._lock = asyncio.Semaphore(1)

    @property
    def name(self) -> str:
        return "whisper"

    @property
    def model_name(self) -> str:
        suffix = f" ({self._backend_name})" if self._backend_name else ""
        return f"{self._model_id}{suffix}"

    def _load_model(self) -> None:
        if self._backend is not None:
            return

        self._backend_name = _detect_backend(self._device)
        logger.info(f"Whisper backend: {self._backend_name}")

        if self._backend_name == "faster-whisper":
            self._backend = _FasterWhisperBackend(
                self._model_id, self._device, self._compute_type
            )
        else:
            self._backend = _TransformersBackend(
                self._model_id, self._device, self._compute_type
            )

    async def transcribe(
        self, audio_data: bytes, language: str = "ja"
    ) -> TranscriptionResult:
        async with self._lock:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._transcribe_sync, audio_data, language
            )

    def _transcribe_sync(
        self, audio_data: bytes, language: str
    ) -> TranscriptionResult:
        self._load_model()
        data, sr = sf.read(io.BytesIO(audio_data), dtype="float32")
        return self._backend.transcribe(data, sr, language, self._beam_size)

    async def is_available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401

            return True
        except ImportError:
            pass
        try:
            import transformers  # noqa: F401

            return True
        except ImportError:
            return False
