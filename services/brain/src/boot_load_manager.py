"""
Boot Load Manager — pre-dawn heavy LLM processing before the user wakes up.

State machine:
  IDLE    — default; nothing running
  RUNNING — background asyncio.Task executing heavy LLM + TTS
  READY   — cache is complete; waiting for wake_up event

Triggered by cognitive_cycle() when:
  - PowerModeManager is in SLEEP mode (is_low_power == True)
  - schedule_learner.get_wake_time() returns a timestamp within BOOT_LOAD_WINDOW_SEC

On wake_up event, EventAutomation checks is_ready and plays cached audio via
VoiceEvent injection, bypassing LLM and TTS entirely.
"""
import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import aiohttp
from loguru import logger

from brain_utils import AUTH_HEADERS as _AUTH_HEADERS, SPEAK_CHUNK_LIMIT, split_for_speak as _split_for_speak

BOOT_LOAD_WINDOW_SEC = int(os.getenv("BOOT_LOAD_WINDOW_SEC", "2700"))  # 45 min
BOOT_LOAD_NEWS_STALE_HOURS = int(os.getenv("BOOT_LOAD_NEWS_STALE_HOURS", "20"))
BOOT_LOAD_MAX_TOKENS = int(os.getenv("BOOT_LOAD_MAX_TOKENS", "1600"))  # thinking uses ~1200, response ~400


@dataclass
class BootLoadCache:
    briefing_chunks: list[str] = field(default_factory=list)  # speak 用テキストチャンク
    audio_urls: list[str] = field(default_factory=list)        # 事前合成済み MP3 URL
    news_chunks: list[str] = field(default_factory=list)       # ニュース個別チャンク
    generated_at: float = 0.0
    is_complete: bool = False


class BootLoadState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    READY = "ready"


class BootLoadManager:
    """Pre-dawn boot loading: heavy LLM + TTS synthesis before predicted wake time."""

    def __init__(self):
        self._state: BootLoadState = BootLoadState.IDLE
        self._cache: Optional[BootLoadCache] = None
        self._task: Optional[asyncio.Task] = None
        self._last_run_date: Optional[str] = None  # YYYY-MM-DD

    # ------------------------------------------------------------------ #
    #  Public interface                                                    #
    # ------------------------------------------------------------------ #

    @property
    def is_running(self) -> bool:
        return self._state == BootLoadState.RUNNING

    @property
    def is_ready(self) -> bool:
        return (
            self._state == BootLoadState.READY
            and self._cache is not None
            and self._cache.is_complete
        )

    @property
    def cache(self) -> Optional[BootLoadCache]:
        return self._cache

    @property
    def state(self) -> BootLoadState:
        return self._state

    def should_start(self, schedule_learner, now: float = None) -> bool:
        """Return True if boot load should start now.

        Conditions:
          - Not already running or ready
          - Has not run today
          - Predicted wake time is within BOOT_LOAD_WINDOW_SEC
        """
        if self._state != BootLoadState.IDLE:
            return False
        if schedule_learner is None:
            return False

        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_run_date == today:
            return False

        wake_ts = schedule_learner.get_wake_time()
        if wake_ts is None:
            return False

        remaining = wake_ts - (now or time.time())
        return 0 < remaining < BOOT_LOAD_WINDOW_SEC

    def start(
        self,
        world_model,
        llm_router,
        voice_url: str,
        news_url: str,
        backend_url: str,
        session: aiohttp.ClientSession,
    ) -> asyncio.Task:
        """Launch boot load as a background asyncio.Task (fire-and-forget)."""
        self._state = BootLoadState.RUNNING
        self._cache = BootLoadCache()
        self._last_run_date = datetime.now().strftime("%Y-%m-%d")

        self._task = asyncio.create_task(
            self._run(world_model, llm_router, voice_url, news_url, backend_url, session)
        )
        return self._task

    def reset(self):
        """Reset state after wake_up event has consumed the cache."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._state = BootLoadState.IDLE
        self._cache = None

    # ------------------------------------------------------------------ #
    #  Internal pipeline                                                   #
    # ------------------------------------------------------------------ #

    async def _run(
        self,
        world_model,
        llm_router,
        voice_url: str,
        news_url: str,
        backend_url: str,
        session: aiohttp.ClientSession,
    ):
        try:
            logger.info("[BootLoad] 起動: 起床前ブリーフィング事前生成開始")

            # Step 1: Ensure news cache is fresh
            news_chunks = await self._fetch_news(news_url, world_model, session)
            self._cache.news_chunks = news_chunks

            # Step 2: Collect today's schedule from world model
            schedule_text = _build_schedule_summary(world_model)

            # Step 3: Generate integrated morning briefing via heavy LLM
            briefing_text = await self._generate_briefing(
                llm_router, world_model, news_chunks, schedule_text
            )
            self._cache.briefing_chunks = _split_for_speak(briefing_text)
            logger.info(
                "[BootLoad] ブリーフィング生成完了: %d チャンク",
                len(self._cache.briefing_chunks),
            )

            # Step 4: Pre-synthesize audio (best-effort; silently skips on failure)
            if voice_url and self._cache.briefing_chunks:
                self._cache.audio_urls = await self._presynthesize(
                    voice_url, self._cache.briefing_chunks, session
                )
                logger.info(
                    "[BootLoad] TTS事前合成完了: %d / %d ファイル",
                    len(self._cache.audio_urls),
                    len(self._cache.briefing_chunks),
                )

            self._cache.generated_at = time.time()
            self._cache.is_complete = True
            self._state = BootLoadState.READY
            logger.info("[BootLoad] 完了 → Boot Ready 状態に移行")

        except asyncio.CancelledError:
            logger.warning("[BootLoad] キャンセル (ユーザーが先に起床)")
            self._state = BootLoadState.IDLE
            raise
        except Exception as e:
            logger.error(f"[BootLoad] 失敗: {e}")
            self._state = BootLoadState.IDLE

    async def _fetch_news(
        self,
        news_url: str,
        world_model,
        session: aiohttp.ClientSession,
    ) -> list[str]:
        """Refresh news if cache is stale; return available chunks."""
        if not news_url:
            return []

        # Check cache freshness
        try:
            ns = world_model.news_state
            age_hours = (time.time() - ns.daily_timestamp) / 3600
            if age_hours <= BOOT_LOAD_NEWS_STALE_HOURS:
                logger.debug(
                    "[BootLoad] ニュースキャッシュは新鮮 (%.1fh前), スキップ", age_hours
                )
                return list(ns.daily_chunks)
        except Exception:
            pass

        # Request refresh
        try:
            async with session.post(
                f"{news_url}/api/news/refresh",
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                if resp.status == 200:
                    logger.info("[BootLoad] ニュース更新完了")
                else:
                    logger.warning("[BootLoad] ニュース更新失敗: HTTP %d", resp.status)
        except Exception as e:
            logger.warning(f"[BootLoad] ニュース更新エラー: {e}")

        # Fetch latest (may be the freshly generated summary)
        try:
            async with session.get(
                f"{news_url}/api/news/latest",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("chunks", [])
        except Exception as e:
            logger.warning(f"[BootLoad] ニュース取得エラー: {e}")

        return []

    async def _generate_briefing(
        self,
        llm_router,
        world_model,
        news_chunks: list[str],
        schedule_text: str,
    ) -> str:
        """Generate an integrated morning briefing via the heavy LLM."""
        now = datetime.now()
        context_parts = [f"現在時刻: {now.strftime('%H:%M')}"]

        try:
            w = world_model.physical.weather
            if w.condition and w.condition != "unknown":
                context_parts.append(f"天気: {w.condition}")
                if w.temperature:
                    context_parts.append(f"気温: {w.temperature}°C")
        except Exception:
            pass

        try:
            bio = world_model.biometric_state
            if bio.sleep.last_update > 0:
                context_parts.append(
                    f"昨夜の睡眠: {bio.sleep.duration_minutes}分"
                    f" (品質 {bio.sleep.quality_score}/100)"
                )
        except Exception:
            pass

        if schedule_text:
            context_parts.append(f"今日の予定:\n{schedule_text}")

        if news_chunks:
            context_parts.append(f"ニュース概要:\n" + "\n".join(news_chunks[:5]))

        context = "\n".join(context_parts)
        prompt = (
            "以下の情報を元に、自然な朝のブリーフィングを生成してください。\n"
            "・起床の挨拶から始め、天気→今日の予定→ニュース→締めの言葉の順で\n"
            "・合計200〜300文字程度、口語体で\n"
            "・テキストのみ出力（説明や括弧書きなし）\n\n"
            f"{context}"
        )

        try:
            response = await llm_router.chat(
                [
                    {
                        "role": "system",
                        "content": "あなたは家庭環境AIアシスタントです。簡潔で自然な日本語で話してください。",
                    },
                    {"role": "user", "content": prompt},
                ],
                task_type="boot_load",
                temperature=0.7,
                max_tokens=BOOT_LOAD_MAX_TOKENS,
            )
            if not response.error and response.content:
                return response.content.strip()
        except Exception as e:
            logger.warning(f"[BootLoad] ブリーフィング生成LLMエラー: {e}")

        # Minimal fallback
        greeting = "おはようございます。" if now.hour < 12 else "こんにちは。"
        try:
            w = world_model.physical.weather
            if w.condition and w.condition != "unknown":
                return f"{greeting}今日の天気は{w.condition}です。"
        except Exception:
            pass
        return greeting

    async def _presynthesize(
        self,
        voice_url: str,
        chunks: list[str],
        session: aiohttp.ClientSession,
    ) -> list[str]:
        """Pre-synthesize each chunk via voice-service; return audio_url list."""
        audio_urls: list[str] = []
        for chunk in chunks:
            try:
                async with session.post(
                    f"{voice_url}/api/voice/synthesize",
                    json={"text": chunk, "tone": "caring"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        url = data.get("audio_url", "")
                        if url:
                            audio_urls.append(url)
            except Exception as e:
                logger.warning(
                    f"[BootLoad] TTS事前合成エラー (chunk: {chunk[:20]}…): {e}"
                )
        return audio_urls


# ------------------------------------------------------------------ #
#  Helpers (module-level, reusable)                                   #
# ------------------------------------------------------------------ #

def _build_schedule_summary(world_model) -> str:
    """Extract today's calendar events as a plain-text summary."""
    try:
        events = world_model.digital.gas_state.calendar_events
        if not events:
            return ""
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        today_end = today_start + 86400
        today_events = [
            ev for ev in events
            if today_start <= ev.start_ts < today_end
        ]
        if not today_events:
            return ""
        lines = []
        for ev in sorted(today_events, key=lambda e: e.start_ts):
            t = datetime.fromtimestamp(ev.start_ts).strftime("%H:%M")
            lines.append(f"- {t} {ev.title}")
        return "\n".join(lines)
    except Exception:
        return ""


