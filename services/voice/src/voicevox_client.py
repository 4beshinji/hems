import aiohttp
import random
from pathlib import Path
from loguru import logger
import io
from pydub import AudioSegment

class VoicevoxClient:
    """Client for VOICEVOX speech synthesis API."""

    # ナースロボ＿タイプＴ style variants
    SPEAKER_NORMAL = 47    # ノーマル
    SPEAKER_HAPPY = 48     # 楽しい
    SPEAKER_COOL = 46      # クール
    SPEAKER_WHISPER = 49   # ささやき

    # Default speaker for general announcements
    SPEAKER_ID = SPEAKER_NORMAL

    # Speaker pools for different contexts
    ANNOUNCEMENT_SPEAKERS = [SPEAKER_NORMAL]
    REJECTION_SPEAKERS = [SPEAKER_NORMAL, SPEAKER_COOL]
    COMPLETION_SPEAKERS = [SPEAKER_NORMAL, SPEAKER_HAPPY]

    @classmethod
    def pick_speaker(cls, context: str = "announcement") -> int:
        """Pick a speaker ID appropriate for the given context."""
        pool = {
            "announcement": cls.ANNOUNCEMENT_SPEAKERS,
            "rejection": cls.REJECTION_SPEAKERS,
            "completion": cls.COMPLETION_SPEAKERS,
        }.get(context, cls.ANNOUNCEMENT_SPEAKERS)
        return random.choice(pool)
    
    def __init__(self, base_url: str = "http://voicevox:50021"):
        self.base_url = base_url
        logger.info(f"VoicevoxClient initialized with base_url: {base_url}")
    
    async def synthesize(
        self, 
        text: str, 
        speaker_id: int = None
    ) -> bytes:
        """
        Synthesize speech using VOICEVOX API.
        
        Args:
            text: Text to synthesize
            speaker_id: Voice character ID (default: ナースロボ＿タイプＴ)
        
        Returns:
            WAV audio data as bytes
        """
        if speaker_id is None:
            speaker_id = self.SPEAKER_ID
            
        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Generate audio query
                query_url = f"{self.base_url}/audio_query"
                params = {"text": text, "speaker": speaker_id}
                
                logger.debug(f"Generating audio query for text: {text[:50]}...")
                async with session.post(query_url, params=params) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"Audio query failed: {error_text}")
                    query = await resp.json()
                
                # Step 2: Synthesize audio
                synthesis_url = f"{self.base_url}/synthesis"
                params = {"speaker": speaker_id}
                
                logger.debug("Synthesizing audio...")
                async with session.post(
                    synthesis_url, 
                    json=query, 
                    params=params
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"Synthesis failed: {error_text}")
                    audio_data = await resp.read()
                
                logger.info(f"Successfully synthesized {len(audio_data)} bytes of audio")
                return audio_data
                
        except Exception as e:
            logger.error(f"VOICEVOX synthesis error: {e}")
            raise
    
    async def save_audio(self, audio_data: bytes, filepath: Path):
        """Save audio data to MP3 file (converted from WAV)."""
        try:
            # Load WAV from bytes
            wav_io = io.BytesIO(audio_data)
            audio_segment = AudioSegment.from_wav(wav_io)
            
            # Export to MP3
            audio_segment.export(filepath, format="mp3", bitrate="64k")
            
            logger.info(f"Successfully converted and saved MP3 to {filepath} (Size: {filepath.stat().st_size} bytes)")
        except Exception as e:
            logger.error(f"Failed to convert or save audio: {e}")
            raise
