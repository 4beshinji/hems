"""
sherpa-onnx STT provider.
NVIDIA Parakeet TDT-CTC 0.6B JP via ONNX Runtime.
Japanese-only, very fast inference.
"""
import asyncio
import io
import os
import struct
import wave

from loguru import logger

from stt_provider import STTProvider, TranscriptionResult

_DEFAULT_MODEL = "sherpa-onnx-nemo-parakeet-tdt_ctc-0.6b-ja"


class SherpaOnnxProvider(STTProvider):
    def __init__(self) -> None:
        self._model_id = os.getenv("STT_MODEL", _DEFAULT_MODEL)
        self._model_dir = os.getenv("STT_MODEL_DIR", "/app/models")
        self._recognizer = None
        self._lock = asyncio.Semaphore(1)

    @property
    def name(self) -> str:
        return "sherpa-onnx"

    @property
    def model_name(self) -> str:
        return self._model_id

    def _load_model(self):
        if self._recognizer is not None:
            return
        import sherpa_onnx

        model_path = os.path.join(self._model_dir, self._model_id)
        if not os.path.isdir(model_path):
            logger.info(f"Downloading sherpa-onnx model: {self._model_id}")
            _download_model(self._model_id, self._model_dir)

        logger.info(f"Loading sherpa-onnx model from: {model_path}")
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            tokens=os.path.join(model_path, "tokens.txt"),
            encoder=os.path.join(model_path, "encoder.onnx"),
            decoder=os.path.join(model_path, "decoder.onnx"),
            joiner=os.path.join(model_path, "joiner.onnx"),
            num_threads=4,
            sample_rate=16000,
            feature_dim=80,
        )
        logger.info("sherpa-onnx model loaded")

    async def transcribe(
        self, audio_data: bytes, language: str = "ja"
    ) -> TranscriptionResult:
        if language != "ja" and language != "auto":
            return TranscriptionResult(
                text="",
                language=language,
                confidence=0.0,
                duration_seconds=0.0,
            )

        async with self._lock:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._transcribe_sync, audio_data
            )

    def _transcribe_sync(self, audio_data: bytes) -> TranscriptionResult:
        self._load_model()
        import sherpa_onnx

        # Read WAV samples
        with wave.open(io.BytesIO(audio_data), "rb") as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
            samples = [s / 32768.0 for s in struct.unpack(f"<{n_frames}h", raw)]

        duration = len(samples) / sr

        stream = self._recognizer.create_stream()
        stream.accept_waveform(sr, samples)
        self._recognizer.decode_stream(stream)

        text = stream.result.text.strip()

        return TranscriptionResult(
            text=text,
            language="ja",
            confidence=0.9 if text else 0.0,
            duration_seconds=duration,
        )

    async def is_available(self) -> bool:
        try:
            import sherpa_onnx  # noqa: F401
            return True
        except ImportError:
            return False


def _download_model(model_id: str, model_dir: str) -> None:
    """Download sherpa-onnx model from HuggingFace."""
    import subprocess

    url = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{model_id}.tar.bz2"
    subprocess.run(
        ["wget", "-qO-", url, "|", "tar", "xjf", "-", "-C", model_dir],
        shell=False,
        check=True,
    )
