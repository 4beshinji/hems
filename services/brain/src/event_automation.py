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

NEWS_BRIDGE_URL = os.getenv("NEWS_BRIDGE_URL", "")

# Default automations when EVENT_AUTOMATIONS env is not set
DEFAULT_AUTOMATIONS = [
    {"event": "wake_up", "actions": ["morning_greeting", "news_briefing", "weather_report"]},
]

# Max chars per speak call — brain speak tool limit is 70
SPEAK_CHUNK_LIMIT = 70


class EventAutomation:
    """イベント駆動の自動アクション実行."""

    EVENTS = {"wake_up", "arrival", "departure", "scheduled"}
    ACTIONS = {"news_briefing", "morning_greeting", "weather_report", "speak_custom"}

    def __init__(self, tool_executor, world_model, llm_client=None, character=None):
        self.tool_executor = tool_executor
        self.world_model = world_model
        self.llm = llm_client
        self.character = character

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

        for automation in self.automations:
            if automation.get("event") != event_type:
                continue
            actions = automation.get("actions", [])
            for action_name in actions:
                try:
                    await self._execute_action(action_name)
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
                for action_name in automation.get("actions", []):
                    try:
                        await self._execute_action(action_name)
                    except Exception as e:
                        logger.error(f"Scheduled action {action_name} failed: {e}")

    async def _execute_action(self, action_name: str):
        """Execute a single action."""
        if action_name == "news_briefing":
            await self._action_news_briefing()
        elif action_name == "morning_greeting":
            await self._action_morning_greeting()
        elif action_name == "weather_report":
            await self._action_weather_report()
        else:
            logger.warning(f"Unknown action: {action_name}")

    async def _action_news_briefing(self):
        """Fetch news summary from news-bridge and speak chunks."""
        if not NEWS_BRIDGE_URL:
            logger.debug("NEWS_BRIDGE_URL not set, skipping news_briefing")
            return

        # Try REST API first
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
        if not chunks and hasattr(self.world_model, 'news_state'):
            ns = self.world_model.digital.news_state
            if ns.daily_chunks:
                chunks = ns.daily_chunks

        if not chunks:
            logger.info("No news summary available for briefing")
            return

        # Speak intro
        await self.tool_executor.execute("speak", {
            "message": "ニュースをお伝えします。",
            "zone": "home",
            "tone": "neutral",
        })

        # Speak each chunk, re-splitting if needed for 70-char limit
        for chunk in chunks:
            sub_chunks = _split_for_speak(chunk, SPEAK_CHUNK_LIMIT)
            for sub in sub_chunks:
                await self.tool_executor.execute("speak", {
                    "message": sub,
                    "zone": "home",
                    "tone": "neutral",
                })

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
        bio = self.world_model.user.biometrics
        if bio.sleep.last_update > 0:
            quality = bio.sleep.quality_score
            duration = bio.sleep.duration_minutes
            context_parts.append(f"昨夜の睡眠: {duration}分 (品質{quality}/100)")

        context = "\n".join(context_parts)

        message = None
        if self.llm:
            try:
                char_name = getattr(self.character, "name", "") if self.character else ""
                prompt = (
                    f"{'キャラクター名: ' + char_name + chr(10) if char_name else ''}"
                    f"以下の状況に基づいて朝の挨拶を1文（50文字以内）で生成してください。\n"
                    f"セリフのみ出力してください。\n\n{context}"
                )
                response = await self.llm.chat([
                    {"role": "system", "content": "短い日本語の朝の挨拶を生成してください。"},
                    {"role": "user", "content": prompt},
                ])
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

        await self.tool_executor.execute("speak", {
            "message": message,
            "zone": "home",
            "tone": "caring",
        })

    async def _action_weather_report(self):
        """Speak weather summary from world model."""
        w = self.world_model.physical.weather
        if w.last_update == 0:
            logger.debug("No weather data, skipping weather_report")
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
            return

        message = "、".join(parts) + "です。"
        # Truncate if too long
        if len(message) > SPEAK_CHUNK_LIMIT:
            message = message[:SPEAK_CHUNK_LIMIT - 1] + "。"

        await self.tool_executor.execute("speak", {
            "message": message,
            "zone": "home",
            "tone": "neutral",
        })


def _split_for_speak(text: str, limit: int) -> list[str]:
    """Split text into chunks of at most `limit` characters, breaking at sentence ends."""
    if len(text) <= limit:
        return [text]

    import re
    sentences = re.split(r"(?<=。)", text)
    chunks: list[str] = []
    buf = ""
    for s in sentences:
        if not s:
            continue
        if len(buf) + len(s) <= limit:
            buf += s
        else:
            if buf:
                chunks.append(buf)
            # If single sentence is too long, hard-truncate
            if len(s) > limit:
                while s:
                    chunks.append(s[:limit])
                    s = s[limit:]
                buf = ""
            else:
                buf = s
    if buf:
        chunks.append(buf)
    return chunks
