"""
Qwen3-ASR STT provider.
Qwen3-ASR 1.7B via qwen-asr package or transformers.
52 languages, streaming-capable, modern architecture.
"""
import asyncio
import io
import os

import soundfile as sf
from loguru import logger

from stt_provider import STTProvider, TranscriptionResult

_DEFAULT_MODEL = "Qwen/Qwen3-ASR-1.7B"


class Qwen3AsrProvider(STTProvider):
    def __init__(self) -> None:
        self._model_id = os.getenv("STT_MODEL", _DEFAULT_MODEL)
        self._device = os.getenv("STT_DEVICE", "auto")
        self._model = None
        self._processor = None
        self._lock = asyncio.Semaphore(1)

    @property
    def name(self) -> str:
        return "qwen3-asr"

    @property
    def model_name(self) -> str:
        return self._model_id

    def _load_model(self):
        if self._model is not None:
            return

        # Try qwen-asr package first (recommended by Qwen team)
        try:
            self._load_via_qwen_asr()
            return
        except ImportError:
            logger.info("qwen-asr package not found, trying transformers")

        self._load_via_transformers()

    def _load_via_qwen_asr(self):
        from qwen_asr import Qwen3ASR

        logger.info(f"Loading Qwen3-ASR via qwen-asr: {self._model_id}")
        self._model = Qwen3ASR.from_pretrained(
            self._model_id,
            device=self._device,
        )
        self._use_qwen_asr = True
        logger.info("Qwen3-ASR loaded via qwen-asr")

    def _load_via_transformers(self):
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        device = self._device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"

        dtype = torch.float16 if "cuda" in device else torch.float32

        logger.info(f"Loading Qwen3-ASR via transformers: {self._model_id} ({device})")
        self._processor = AutoProcessor.from_pretrained(self._model_id)
        self._model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self._model_id,
            torch_dtype=dtype,
            device_map=device,
            cache_dir=os.getenv("STT_MODEL_DIR", "/app/models"),
        )
        self._use_qwen_asr = False
        logger.info("Qwen3-ASR loaded via transformers")

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
        duration = len(data) / sr

        if hasattr(self, "_use_qwen_asr") and self._use_qwen_asr:
            return self._transcribe_qwen_asr(data, sr, language, duration)

        return self._transcribe_transformers(data, sr, language, duration)

    def _transcribe_qwen_asr(
        self, data, sr: int, language: str, duration: float
    ) -> TranscriptionResult:
        result = self._model.transcribe(
            data,
            sr=sr,
            language=None if language == "auto" else language,
        )
        text = result.get("text", "") if isinstance(result, dict) else str(result)

        return TranscriptionResult(
            text=text.strip(),
            language=result.get("language", language)
            if isinstance(result, dict)
            else language,
            confidence=0.9 if text else 0.0,
            duration_seconds=duration,
        )

    def _transcribe_transformers(
        self, data, sr: int, language: str, duration: float
    ) -> TranscriptionResult:
        import torch

        inputs = self._processor(
            data,
            sampling_rate=sr,
            return_tensors="pt",
        )
        inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

        with torch.no_grad():
            generated_ids = self._model.generate(
                **inputs,
                max_new_tokens=448,
                language=None if language == "auto" else language,
            )

        text = self._processor.batch_decode(
            generated_ids, skip_special_tokens=True
        )[0]

        return TranscriptionResult(
            text=text.strip(),
            language=language,
            confidence=0.9 if text else 0.0,
            duration_seconds=duration,
        )

    async def is_available(self) -> bool:
        try:
            import qwen_asr  # noqa: F401
            return True
        except ImportError:
            pass
        try:
            import transformers  # noqa: F401
            return True
        except ImportError:
            return False
