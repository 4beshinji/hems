"""
Microsoft Edge TTS Provider — free cloud TTS.
"""
import io
from loguru import logger
from tts_provider import TTSProvider, AudioResult

VOICE_MAP = {
    "neutral": "ja-JP-NanamiNeural",
    "caring": "ja-JP-NanamiNeural",
    "humorous": "ja-JP-KeitaNeural",
    "alert": "ja-JP-NanamiNeural",
    "happy": "ja-JP-NanamiNeural",
}


class EdgeTTSProvider(TTSProvider):
    def __init__(self, config: dict = None):
        self.voices = VOICE_MAP.copy()
        if config and "voices" in config:
            self.voices.update(config["voices"])

    @property
    def name(self) -> str:
        return "edge-tts"

    async def synthesize(self, text: str, voice: str = "neutral", speed: float = 1.0) -> AudioResult:
        import edge_tts

        voice_name = self.voices.get(voice, self.voices["neutral"])
        rate = f"+{int((speed - 1) * 100)}%" if speed >= 1 else f"{int((speed - 1) * 100)}%"

        communicate = edge_tts.Communicate(text, voice_name, rate=rate)
        audio_buffer = io.BytesIO()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.write(chunk["data"])

        return AudioResult(audio_data=audio_buffer.getvalue(), format="mp3")

    async def is_available(self) -> bool:
        try:
            import edge_tts
            return True
        except ImportError:
            return False
