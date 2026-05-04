"""
Event Automation — event-driven action execution for HEMS Brain.
Maps events (wake_up, arrival, departure, scheduled) to actions
(news_briefing, morning_greeting, weather_report).
"""

import json
import os
import time
from datetime import datetime

import aiohttp
from loguru import logger

from brain_utils import SPEAK_CHUNK_LIMIT
from brain_utils import split_for_speak as _split_for_speak

NEWS_BRIDGE_URL = os.getenv("NEWS_BRIDGE_URL", "")
BACKEND_URL = os.getenv("DASHBOARD_API_URL", os.getenv("BACKEND_URL", "http://backend:8000"))
# news cache age beyond which we'll trigger a fresh /api/news/refresh before
# speaking the briefing. BootLoad's own pre-synth refresh keeps the cache
# fresh on most days; this catches the BootLoad-not-fired case (no
# schedule_learner data, fallback wake_up trigger, etc.).
NEWS_REFRESH_STALE_HOURS = float(os.getenv("NEWS_REFRESH_STALE_HOURS", "2"))

# Default automations when EVENT_AUTOMATIONS env is not set
DEFAULT_AUTOMATIONS = [
    {
        "event": "wake_up",
        "actions": ["weather_alert_announce", "morning_greeting", "news_briefing", "weather_report"],
    },
]


class EventAutomation:
    """イベント駆動の自動アクション実行."""

    EVENTS = {"wake_up", "arrival", "departure", "scheduled"}
    ACTIONS = {
        "news_briefing",
        "morning_greeting",
        "weather_report",
        "weather_alert_announce",
        "speak_custom",
        "task_planning",
    }

    def __init__(self, tool_executor, world_model, llm_client=None, character=None, boot_load_manager=None):
        self.tool_executor = tool_executor
        self.world_model = world_model
        self.llm = llm_client
        self.character = character
        self.boot_load_manager = boot_load_manager

        # Parse automations from env or use defaults
        raw = os.getenv("EVENT_AUTOMATIONS", "")
        if raw:
            try:
                self.automations = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid EVENT_AUTOMATIONS JSON, using defaults")
                self.automations = DEFAULT_AUTOMATIONS
        else:
            self.automations = DEFAULT_AUTOMATIONS

        # Cooldowns: {event_type: last_trigger_timestamp}
        self._cooldowns: dict[str, float] = {}
        # Daily cooldowns: {event_type: date_string}
        self._daily_cooldowns: dict[str, str] = {}

        # Scheduled event tracking: {time_str: last_run_date}
        self._scheduled_runs: dict[str, str] = {}

        self._session: aiohttp.ClientSession | None = None

    def set_session(self, session: aiohttp.ClientSession):
        self._session = session

    def _check_cooldown_daily(self, event_type: str) -> bool:
        """Return True if event has NOT fired today yet."""
        today = datetime.now().strftime("%Y-%m-%d")
        last = self._daily_cooldowns.get(event_type)
        if last == today:
            return False
        return True

    def _record_daily(self, event_type: str):
        """Record that event fired today."""
        self._daily_cooldowns[event_type] = datetime.now().strftime("%Y-%m-%d")

    async def trigger(self, event_type: str):
        """Trigger all automations matching the given event type."""
        if event_type not in self.EVENTS:
            logger.warning(f"Unknown event type: {event_type}")
            return

        # Daily debounce for wake_up/arrival/departure
        if event_type in ("wake_up", "arrival", "departure"):
            if not self._check_cooldown_daily(event_type):
                logger.debug(f"Event {event_type} already fired today, skipping")
                return
            self._record_daily(event_type)

        logger.info(f"Event triggered: {event_type}")

        # Boot Load cache: play pre-generated briefing instantly if ready.
        # Voice actions (greeting/news/weather) are replaced by the cache,
        # but device actions (scene:*) still run below.
        boot_load_used = False
        if event_type == "wake_up" and self.boot_load_manager and self.boot_load_manager.is_ready:
            logger.info("[BootLoad] キャッシュ済みブリーフィングを再生")
            try:
                await self._execute_boot_load_briefing()
                boot_load_used = True
                self.boot_load_manager.reset()
            except Exception as e:
                logger.error(f"[BootLoad] キャッシュ再生失敗、通常パスにフォールバック: {e}")

        # Voice-only actions that boot load already covers
        _BOOT_LOAD_ACTIONS = {"morning_greeting", "news_briefing", "weather_report"}

        for automation in self.automations:
            if automation.get("event") != event_type:
                continue
            actions = automation.get("actions", [])
            for action in actions:
                action_name = action if isinstance(action, str) else action.get("name", "")
                action_config = None if isinstance(action, str) else action
                # Skip voice actions already played by boot load cache
                if boot_load_used and action_name in _BOOT_LOAD_ACTIONS:
                    continue
                try:
                    await self._execute_action(action_name, action_config)
                except Exception as e:
                    logger.error(f"Action {action_name} failed: {e}")

    async def check_scheduled(self):
        """Check if any scheduled automations should fire now."""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")

        for automation in self.automations:
            if automation.get("event") != "scheduled":
                continue
            target_time = automation.get("time", "")
            if not target_time:
                continue

            if current_time == target_time:
                if self._scheduled_runs.get(target_time) == today:
                    continue
                self._scheduled_runs[target_time] = today
                logger.info(f"Scheduled event fired: {target_time}")
                for action in automation.get("actions", []):
                    action_name = action if isinstance(action, str) else action.get("name", "")
                    action_config = None if isinstance(action, str) else action
                    try:
                        await self._execute_action(action_name, action_config)
                    except Exception as e:
                        logger.error(f"Scheduled action {action_name} failed: {e}")

    async def _execute_action(self, action_name: str, action_config: dict = None):
        """Execute a single action."""
        # scene:{name} → route to Scene executor
        if action_name.startswith("scene:"):
            scene_name = action_name.split(":", 1)[1]
            await self.tool_executor.execute(
                "execute_scene_by_name",
                {"name": scene_name},
            )
            return

        if action_name == "news_briefing":
            await self._action_news_briefing()
        elif action_name == "morning_greeting":
            await self._action_morning_greeting()
        elif action_name == "weather_report":
            await self._action_weather_report()
        elif action_name == "weather_alert_announce":
            await self._action_weather_alert_announce()
        elif action_name == "task_planning":
            await self._action_task_planning()
        elif action_name == "speak_custom":
            text = (action_config or {}).get("text", "")
            if text:
                await self.tool_executor.execute(
                    "speak",
                    {
                        "message": text[:SPEAK_CHUNK_LIMIT],
                        "zone": "home",
                        "tone": (action_config or {}).get("tone", "neutral"),
                    },
                )
        else:
            logger.warning(f"Unknown action: {action_name}")

    async def _action_news_briefing(self):
        """Fetch news summary from news-bridge and speak chunks.

        Triggers a fresh /api/news/refresh first if the cached daily summary
        is older than NEWS_REFRESH_STALE_HOURS. BootLoad pre-synth normally
        keeps it fresh; this branch covers wake_up paths where BootLoad
        did not fire (no schedule_learner data, fallback trigger, restart).
        """
        if not NEWS_BRIDGE_URL:
            logger.debug("NEWS_BRIDGE_URL not set, skipping news_briefing")
            return

        # Check cache freshness; trigger refresh if stale (BootLoad-friendly
        # because BootLoad already refreshed sets daily_timestamp recently,
        # so this branch is skipped naturally).
        if self._session and hasattr(self.world_model, "news_state"):
            ns = self.world_model.news_state
            age_hours = (time.time() - ns.daily_timestamp) / 3600 if ns.daily_timestamp else 9999
            if age_hours > NEWS_REFRESH_STALE_HOURS:
                logger.info(
                    f"[news_briefing] cache stale ({age_hours:.1f}h > {NEWS_REFRESH_STALE_HOURS}h) "
                    f"→ trigger refresh"
                )
                try:
                    async with self._session.post(
                        f"{NEWS_BRIDGE_URL}/api/news/refresh",
                        timeout=aiohttp.ClientTimeout(total=90),
                    ) as resp:
                        if resp.status != 200:
                            logger.warning(f"News refresh returned {resp.status}")
                except Exception as e:
                    logger.warning(f"News refresh failed: {e}")

        # Try REST API for the latest summary
        chunks = []
        if self._session:
            try:
                async with self._session.get(
                    f"{NEWS_BRIDGE_URL}/api/news/latest",
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        chunks = data.get("chunks", [])
                    else:
                        logger.warning(f"News bridge returned {resp.status}")
            except Exception as e:
                logger.warning(f"News bridge request failed: {e}")

        # Fallback: use cached summary from world model
        if not chunks and hasattr(self.world_model, "news_state"):
            ns = self.world_model.news_state
            if ns.daily_chunks:
                chunks = ns.daily_chunks

        if not chunks:
            logger.info("No news summary available for briefing")
            return

        # Speak intro
        await self.tool_executor.execute(
            "speak",
            {
                "message": "ニュースをお伝えします。",
                "zone": "home",
                "tone": "neutral",
            },
        )

        # Speak each chunk, re-splitting if needed for 70-char limit
        for chunk in chunks:
            sub_chunks = _split_for_speak(chunk)
            for sub in sub_chunks:
                await self.tool_executor.execute(
                    "speak",
                    {
                        "message": sub,
                        "zone": "home",
                        "tone": "neutral",
                    },
                )

    async def _action_morning_greeting(self):
        """Generate and speak a morning greeting using LLM."""
        now = datetime.now()
        context_parts = [f"時刻: {now.strftime('%H:%M')}"]

        # Weather
        w = self.world_model.physical.weather
        if w.condition and w.condition != "unknown":
            context_parts.append(f"天気: {w.condition}")
            if w.temperature:
                context_parts.append(f"外気温: {w.temperature}°C")

        # Biometrics
        bio = self.world_model.biometric_state
        if bio.sleep.last_update > 0:
            quality = bio.sleep.quality_score
            duration = bio.sleep.duration_minutes
            context_parts.append(f"昨夜の睡眠: {duration}分 (品質{quality}/100)")

        context = "\n".join(context_parts)

        message = None
        if self.llm:
            try:
                # Stage 1: factual morning greeting (no character injection).
                # Character voice is applied later via _handle_speak → PersonaRewriter.
                prompt = (
                    f"以下の状況に基づいて朝の挨拶を1文（50文字以内）で、"
                    f"素のまま事実ベースで生成してください。"
                    f"キャラ口調や装飾語尾は付けないでください（後段で付与されます）。\n"
                    f"セリフのみ出力してください。\n\n{context}"
                )
                response = await self.llm.chat(
                    [
                        {"role": "system", "content": "短い日本語の朝の挨拶を素のまま生成してください。"},
                        {"role": "user", "content": prompt},
                    ]
                )
                if not response.error and response.content:
                    message = response.content.strip().strip("「」『』\"'")[:67]
            except Exception as e:
                logger.warning(f"Morning greeting LLM failed: {e}")

        if not message:
            hour = now.hour
            if hour < 10:
                message = "おはようございます。今日も良い一日を。"
            elif hour < 12:
                message = "おはようございます。良い午前をお過ごしください。"
            else:
                message = "こんにちは。"

        await self.tool_executor.execute(
            "speak",
            {
                "message": message,
                "zone": "home",
                "tone": "caring",
            },
        )

    async def _execute_boot_load_briefing(self):
        """Play pre-generated boot load briefing cache.

        Mixed mode: pre-synthesized chunks are injected as VoiceEvents
        directly into the backend (instant playback via the 3s polling).
        Chunks without audio_url fall back to speak() for at-wake TTS.
        Order is preserved across both paths.
        """
        cache = self.boot_load_manager.cache
        if not cache or not cache.briefing_chunks:
            logger.warning("[BootLoad] キャッシュが空")
            return

        chunks = cache.briefing_chunks
        audio_urls = list(cache.audio_urls or [])

        injected = 0
        spoken = 0
        for idx, chunk in enumerate(chunks):
            url = audio_urls[idx] if idx < len(audio_urls) else None
            if url and self._session:
                try:
                    async with self._session.post(
                        f"{BACKEND_URL}/voice-events/",
                        json={
                            "message": chunk,
                            "audio_url": url,
                            "zone": "home",
                            "tone": "caring",
                        },
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status in (200, 201):
                            injected += 1
                            continue
                        logger.warning("[BootLoad] VoiceEvent inject HTTP %d", resp.status)
                except Exception as e:
                    logger.warning(f"[BootLoad] VoiceEvent inject エラー: {e}")
                # fall through to speak() if injection failed

            # No audio_url (or injection failed) → at-wake TTS
            try:
                await self.tool_executor.execute(
                    "speak",
                    {"message": chunk, "zone": "home", "tone": "caring"},
                )
                spoken += 1
            except Exception as e:
                logger.warning(f"[BootLoad] speak エラー: {e}")

        logger.info(
            "[BootLoad] 再生完了: injected=%d spoken=%d total=%d",
            injected,
            spoken,
            len(chunks),
        )

    async def _action_task_planning(self):
        """アクティブタスクの詳細プランを LLM で生成し、結果を発話する。"""
        if not self.llm:
            logger.debug("[task_planning] LLM未設定、スキップ")
            return
        try:
            tasks = await self.tool_executor.dashboard.get_active_tasks()
            if not tasks:
                logger.info("[task_planning] アクティブタスクなし")
                await self.tool_executor.execute(
                    "speak",
                    {
                        "message": "現在アクティブなタスクはありません。",
                        "zone": "home",
                        "tone": "neutral",
                    },
                )
                return

            tasks_text = "\n".join(f"- [{t['id']}] {t['title']}: {t.get('description', '')}" for t in tasks[:10])
            prompt = (
                f"以下のアクティブタスクについて、各タスクの詳細な実行手順・目安時間・注意点を"
                f"日本語で簡潔にまとめてください。発話用なので200文字以内でお願いします。\n\n{tasks_text}"
            )
            resp = await self.llm.chat(
                [
                    {"role": "system", "content": "あなたはタスク管理アシスタントです。簡潔に答えてください。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
            )
            if resp.error:
                logger.warning("[task_planning] LLMエラー: %s", resp.error)
                return

            content = resp.content.strip()
            if content:
                for chunk in _split_for_speak(content, SPEAK_CHUNK_LIMIT):
                    await self.tool_executor.execute(
                        "speak",
                        {
                            "message": chunk,
                            "zone": "home",
                            "tone": "informative",
                        },
                    )
            logger.info("[task_planning] 完了 (%d tasks)", len(tasks))
        except Exception as e:
            logger.error("[task_planning] エラー: %s", e)

    async def _action_weather_alert_announce(self):
        """Announce active weather alerts (warning+ severity)."""
        w = self.world_model.physical.weather
        severe_levels = {"warning", "severe", "extreme", "critical"}
        active = [
            a for a in w.alerts
            if (a.severity or "").lower() in severe_levels and a.title
        ]
        if not active:
            logger.debug("[weather_alert_announce] no active severe alerts")
            return

        for alert in active[:3]:
            area_part = f"（{alert.area}）" if alert.area else ""
            message = f"気象警報: {alert.title}{area_part}。注意してください。"
            for chunk in _split_for_speak(message, SPEAK_CHUNK_LIMIT):
                await self.tool_executor.execute(
                    "speak",
                    {
                        "message": chunk,
                        "zone": "home",
                        "tone": "alert",
                    },
                )

    async def _action_weather_report(self):
        """Speak weather summary from world model."""
        w = self.world_model.physical.weather
        if w.last_update == 0:
            logger.warning("weather_report: weather-bridge data not yet received")
            await self.tool_executor.execute(
                "speak",
                {
                    "message": "天気情報はまだ取得できていません。",
                    "zone": "home",
                    "tone": "neutral",
                },
            )
            return

        parts = []
        if w.condition and w.condition != "unknown":
            parts.append(f"現在の天気は{w.condition}")
        if w.temperature:
            parts.append(f"気温{w.temperature}度")
        if w.humidity:
            parts.append(f"湿度{w.humidity}パーセント")

        # Check forecast for rain
        rain_forecast = None
        for f in w.forecast[:6]:
            if f.precipitation_probability and f.precipitation_probability > 50:
                rain_forecast = f
                break

        if rain_forecast:
            parts.append(f"この後、{rain_forecast.datetime}頃に雨の可能性があります")

        if not parts:
            logger.info("weather_report: data present but all fields empty, skipping")
            return

        message = "、".join(parts) + "です。"
        # Truncate if too long
        if len(message) > SPEAK_CHUNK_LIMIT:
            message = message[: SPEAK_CHUNK_LIMIT - 1] + "。"

        await self.tool_executor.execute(
            "speak",
            {
                "message": message,
                "zone": "home",
                "tone": "neutral",
            },
        )
