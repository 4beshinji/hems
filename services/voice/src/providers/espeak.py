"""
espeak-ng TTS Provider — lightweight fallback.
"""
import asyncio
import tempfile
from pathlib import Path
from loguru import logger
from tts_provider import TTSProvider, AudioResult


class EspeakProvider(TTSProvider):
    def __init__(self, config: dict = None):
        self.voice = "ja" if not config else config.get("voice", "ja")
        self.pitch = 50 if not config else config.get("pitch", 50)

    @property
    def name(self) -> str:
        return "espeak"

    async def synthesize(self, text: str, voice: str = "neutral", speed: float = 1.0) -> AudioResult:
        wpm = int(175 * speed)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmpfile = f.name

        proc = await asyncio.create_subprocess_exec(
            "espeak-ng", "-v", self.voice, "-s", str(wpm), "-p", str(self.pitch),
            "-w", tmpfile, text,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        audio_data = Path(tmpfile).read_bytes()
        Path(tmpfile).unlink(missing_ok=True)

        return AudioResult(audio_data=audio_data, format="wav", sample_rate=22050)

    async def is_available(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "espeak-ng", "--version",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False
