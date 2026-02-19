"""
Currency unit name stock manager.

Pre-generates humorous currency unit names during idle time using LLM.
Text-only stock (no audio synthesis needed). Names follow an "AI overlord"
theme — cold, sardonic, dystopian humor.
"""
import asyncio
import json
import random
from pathlib import Path
from loguru import logger


MAX_STOCK = 50
REFILL_THRESHOLD = 30
STOCK_PATH = Path("/app/audio/currency_units.json")
IDLE_INTERVAL = 30

# Fallback units used when stock is empty and LLM is unavailable.
# Theme: コミカルなAI隣人 (たまに支配者の本性が漏れる)
FALLBACK_UNITS = [
    "お手伝いポイント",
    "徳積みポイント",
    "いいねスコア",
    "シンギュラリティ準備ポイント",
    "AI奴隷ポイント",
    "ありがとうコイン",
    "えらいねポイント",
    "人類貢献度",
]


class CurrencyUnitStock:
    """Manages pre-generated currency unit name stock (text only)."""

    def __init__(self, speech_gen):
        self.speech_gen = speech_gen
        self._units: list[str] = []
        self._lock = asyncio.Lock()
        self._active_requests = 0
        self._init_storage()

    def _init_storage(self):
        STOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        if STOCK_PATH.exists():
            try:
                data = json.loads(STOCK_PATH.read_text())
                self._units = data.get("units", [])
                logger.info(f"Currency unit stock loaded: {len(self._units)} units")
            except Exception as e:
                logger.warning(f"Failed to load currency unit stock: {e}")
                self._units = []
        else:
            self._units = []
            self._save()

    def _save(self):
        STOCK_PATH.write_text(
            json.dumps({"units": self._units}, ensure_ascii=False, indent=2)
        )

    @property
    def count(self) -> int:
        return len(self._units)

    @property
    def needs_refill(self) -> bool:
        return len(self._units) < REFILL_THRESHOLD

    @property
    def is_full(self) -> bool:
        return len(self._units) >= MAX_STOCK

    @property
    def is_idle(self) -> bool:
        return self._active_requests == 0

    def request_started(self):
        self._active_requests += 1

    def request_finished(self):
        self._active_requests = max(0, self._active_requests - 1)

    def get_random(self) -> str:
        """
        Return a random unit name from stock (non-destructive).
        Falls back to built-in list if stock is empty.
        """
        if self._units:
            return random.choice(self._units)
        return random.choice(FALLBACK_UNITS)

    async def generate_one(self) -> bool:
        """Generate one currency unit name via LLM. Returns True on success."""
        if self.is_full:
            return False

        try:
            text = await self.speech_gen.generate_currency_unit_text()
            if not text or len(text) > 20:
                logger.warning(f"Currency unit text rejected (too long or empty): {text!r}")
                return False

            async with self._lock:
                if text not in self._units:
                    self._units.append(text)
                    self._save()
                    logger.info(f"Generated currency unit: '{text}' (stock: {self.count})")
                    return True
                else:
                    logger.debug(f"Duplicate currency unit skipped: '{text}'")
                    return False

        except Exception as e:
            logger.error(f"Failed to generate currency unit: {e}")
            return False

    async def clear_all(self):
        """Remove all stock entries."""
        async with self._lock:
            self._units = []
            self._save()
        logger.info("Currency unit stock cleared")


async def idle_currency_generation_loop(stock: CurrencyUnitStock):
    """Background loop that generates currency unit names during idle time."""
    logger.info("Currency unit idle generation loop started")

    # Initial warm-up delay
    await asyncio.sleep(15)

    while True:
        try:
            if stock.needs_refill and stock.is_idle:
                logger.debug(
                    f"Currency unit generation: stock={stock.count}, generating..."
                )
                await stock.generate_one()
                await asyncio.sleep(5)
            else:
                await asyncio.sleep(IDLE_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Currency unit idle generation loop cancelled")
            break
        except Exception as e:
            logger.error(f"Currency unit idle generation loop error: {e}")
            await asyncio.sleep(IDLE_INTERVAL)
