"""
Rejection voice stock manager.

Pre-generates rejection/snarky voice lines during idle time using LLM + VOICEVOX.
Maintains a stock of up to MAX_STOCK audio files for instant playback when users
ignore tasks on the dashboard.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger

from speech_generator import SpeechGenerator
from voicevox_client import VoicevoxClient

MAX_STOCK = 100
STOCK_DIR = Path("/app/audio/rejections")
MANIFEST_PATH = STOCK_DIR / "manifest.json"
# Generate when stock is below this threshold
REFILL_THRESHOLD = 80
# Seconds between generation attempts during idle
IDLE_INTERVAL = 30


class RejectionStock:
    """Manages pre-generated rejection voice audio stock."""

    def __init__(self, speech_gen: SpeechGenerator, voice_client: VoicevoxClient):
        self.speech_gen = speech_gen
        self.voice_client = voice_client
        self._entries: list[dict] = []
        self._lock = asyncio.Lock()
        # Tracks number of active voice service requests (non-rejection)
        self._active_requests = 0
        self._init_storage()

    def _init_storage(self):
        STOCK_DIR.mkdir(parents=True, exist_ok=True)
        if MANIFEST_PATH.exists():
            try:
                data = json.loads(MANIFEST_PATH.read_text())
                self._entries = data.get("entries", [])
                # Prune entries whose audio files no longer exist
                self._entries = [
                    e for e in self._entries
                    if (STOCK_DIR / e["audio_file"]).exists()
                ]
                self._save_manifest()
                logger.info(f"Rejection stock loaded: {len(self._entries)} entries")
            except Exception as e:
                logger.warning(f"Failed to load rejection manifest: {e}")
                self._entries = []
        else:
            self._entries = []
            self._save_manifest()

    def _save_manifest(self):
        MANIFEST_PATH.write_text(
            json.dumps({"entries": self._entries}, ensure_ascii=False, indent=2)
        )

    @property
    def count(self) -> int:
        return len(self._entries)

    @property
    def needs_refill(self) -> bool:
        return len(self._entries) < REFILL_THRESHOLD

    @property
    def is_full(self) -> bool:
        return len(self._entries) >= MAX_STOCK

    @property
    def is_idle(self) -> bool:
        return self._active_requests == 0

    def request_started(self):
        self._active_requests += 1

    def request_finished(self):
        self._active_requests = max(0, self._active_requests - 1)

    async def get_random(self) -> dict | None:
        """
        Pop a random entry from the stock and return it.
        Returns None if stock is empty.
        """
        async with self._lock:
            if not self._entries:
                return None
            import random
            idx = random.randrange(len(self._entries))
            entry = self._entries.pop(idx)
            try:
                self._save_manifest()
            except Exception as e:
                self._entries.insert(idx, entry)
                logger.error(f"Failed to save manifest after pop, entry restored: {e}")
                return None
        logger.info(
            f"Served rejection audio: {entry['text']} "
            f"(stock remaining: {self.count})"
        )
        return {
            "audio_url": f"/audio/rejections/{entry['audio_file']}",
            "text": entry["text"],
        }

    async def clear_all(self):
        """Remove all stock entries and their audio files."""
        async with self._lock:
            for entry in self._entries:
                path = STOCK_DIR / entry["audio_file"]
                if path.exists():
                    path.unlink()
            self._entries = []
            self._save_manifest()
        logger.info("Rejection stock cleared")

    async def generate_one(self) -> bool:
        """
        Generate one rejection entry (LLM text + VOICEVOX audio).
        Returns True on success, False on failure.
        """
        if self.is_full:
            return False

        try:
            # 1. Generate rejection text via LLM
            text = await self.speech_gen.generate_rejection_text()

            # 2. Synthesize audio via VOICEVOX (with speaker variation)
            from voicevox_client import VoicevoxClient
            speaker = VoicevoxClient.pick_speaker("rejection")
            audio_data = await self.voice_client.synthesize(text, speaker_id=speaker)

            # 3. Save audio file
            entry_id = str(uuid.uuid4())[:8]
            audio_filename = f"rejection_{entry_id}.mp3"
            audio_path = STOCK_DIR / audio_filename
            await self.voice_client.save_audio(audio_data, audio_path)

            # 4. Add to manifest
            entry = {
                "id": entry_id,
                "text": text,
                "audio_file": audio_filename,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            async with self._lock:
                # Evict oldest if somehow over limit
                while len(self._entries) >= MAX_STOCK:
                    oldest = self._entries.pop(0)
                    old_path = STOCK_DIR / oldest["audio_file"]
                    if old_path.exists():
                        old_path.unlink()
                self._entries.append(entry)
                try:
                    self._save_manifest()
                except Exception as e:
                    self._entries.pop()
                    if audio_path.exists():
                        audio_path.unlink()
                    logger.error(f"Manifest save failed, rolled back entry: {e}")
                    return False

            logger.info(
                f"Generated rejection entry: '{text}' (stock: {self.count})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to generate rejection entry: {e}")
            return False


async def idle_generation_loop(stock: RejectionStock):
    """
    Background loop that generates rejection audio during idle time.
    Runs continuously, sleeping between attempts.
    """
    logger.info("Rejection stock idle generation loop started")

    # Initial warm-up delay to let services start
    await asyncio.sleep(10)

    while True:
        try:
            if stock.needs_refill and stock.is_idle:
                logger.debug(
                    f"Idle generation: stock={stock.count}, "
                    f"generating... (active_requests={stock._active_requests})"
                )
                await stock.generate_one()
                # Short sleep between generations to not monopolize resources
                await asyncio.sleep(3)
            else:
                # Wait longer when stock is healthy or service is busy
                await asyncio.sleep(IDLE_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Idle generation loop cancelled")
            break
        except Exception as e:
            logger.error(f"Idle generation loop error: {e}")
            await asyncio.sleep(IDLE_INTERVAL)
