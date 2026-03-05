"""
HEMS Lite Sentinel — LLM escalation for gray zone situations.
Calls cloud LLM API (OpenAI/Anthropic) only when rules can't decide.
"""
import json
import time
from dataclasses import dataclass
from datetime import datetime, date

import aiohttp
from loguru import logger

from config import (
    LLM_PROVIDER, LLM_API_URL, LLM_API_KEY, LLM_MODEL,
    ANTHROPIC_API_KEY,
    LLM_DAILY_BUDGET, LLM_ESCALATION_COOLDOWN,
    SITE_NAME,
)
from gray_zone import GrayZoneEvent
from state import OccupantState


class EscalationVerdict:
    NOTIFY = "NOTIFY"    # Send alert to caregiver
    WATCH = "WATCH"      # Log but don't notify, check again soon
    IGNORE = "IGNORE"    # Not concerning


@dataclass
class EscalationResult:
    verdict: str          # NOTIFY | WATCH | IGNORE
    level: str            # CRITICAL | HIGH | NORMAL
    reason: str           # LLM's reasoning
    message: str          # Notification message if verdict=NOTIFY
    raw_response: str = ""


SYSTEM_PROMPT = f"""\
You are a health monitoring assistant for "{SITE_NAME}".
You analyze gray-zone sensor readings — situations where individual values are \
within normal range but the combination or pattern may be concerning.

Your role is to assess whether the caregiver should be notified.

Respond with EXACTLY this JSON format:
{{
  "verdict": "NOTIFY" | "WATCH" | "IGNORE",
  "level": "CRITICAL" | "HIGH" | "NORMAL",
  "reason": "Brief reasoning in Japanese (1-2 sentences)",
  "message": "Notification message in Japanese for caregiver (if NOTIFY, else empty)"
}}

Guidelines:
- NOTIFY: Real concern that caregiver should know about. Be specific.
- WATCH: Somewhat unusual but not yet concerning. Will re-check.
- IGNORE: Normal variation, sensor noise, or benign explanation.
- Err on the side of caution for elderly/vulnerable people.
- Consider time of day, activity context, and combined signals.
- Keep messages concise and actionable for a non-medical caregiver.
- Do NOT diagnose medical conditions. Suggest "confirm" or "check on".
"""


class Escalator:
    """Manages LLM calls for gray zone situations with budget control."""

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._daily_calls: int = 0
        self._daily_date: date | None = None
        self._cooldowns: dict[str, float] = {}

    @property
    def llm_available(self) -> bool:
        """Check if LLM escalation is configured."""
        if LLM_PROVIDER == "anthropic":
            return bool(ANTHROPIC_API_KEY)
        return bool(LLM_API_URL and LLM_API_KEY)

    @property
    def budget_remaining(self) -> int:
        self._reset_daily_if_needed()
        return max(0, LLM_DAILY_BUDGET - self._daily_calls)

    async def evaluate(self, event: GrayZoneEvent, state: OccupantState) -> EscalationResult | None:
        """Ask LLM to judge a gray zone event. Returns None if budget exhausted or LLM unavailable."""
        if not self.llm_available:
            logger.debug("LLM not configured, skipping escalation")
            return None

        self._reset_daily_if_needed()
        if self._daily_calls >= LLM_DAILY_BUDGET:
            logger.warning(f"LLM daily budget exhausted ({LLM_DAILY_BUDGET} calls)")
            return None

        # Cooldown per pattern type
        now = time.time()
        cooldown_key = f"{event.pattern}_{hash(tuple(event.signals))}"
        last = self._cooldowns.get(cooldown_key, 0)
        if now - last < LLM_ESCALATION_COOLDOWN:
            return None

        try:
            result = await self._call_llm(event, state)
            self._daily_calls += 1
            self._cooldowns[cooldown_key] = now
            logger.info(
                f"LLM escalation: pattern={event.pattern}, "
                f"verdict={result.verdict}, budget={self.budget_remaining}"
            )
            return result
        except Exception as e:
            logger.error(f"LLM escalation failed: {e}")
            return None

    async def _call_llm(self, event: GrayZoneEvent, state: OccupantState) -> EscalationResult:
        """Make the actual LLM API call."""
        if self._session is None:
            self._session = aiohttp.ClientSession()

        context = state.get_context_summary()
        now = datetime.now()

        user_msg = (
            f"Time: {now.strftime('%Y-%m-%d %H:%M')} ({now.strftime('%A')})\n\n"
            f"Gray zone detected: {event.pattern}\n"
            f"Description: {event.description}\n"
            f"Signals: {json.dumps(event.signals, ensure_ascii=False)}\n"
            f"Confidence: {event.confidence:.0%}\n\n"
            f"Current state:\n{context}\n\n"
            f"Should the caregiver be notified?"
        )

        if LLM_PROVIDER == "anthropic":
            return await self._call_anthropic(user_msg)
        return await self._call_openai(user_msg)

    async def _call_openai(self, user_msg: str) -> EscalationResult:
        url = f"{LLM_API_URL}/chat/completions"
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.3,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {LLM_API_KEY}"}

        async with self._session.post(url, json=payload, headers=headers, timeout=30) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"OpenAI HTTP {resp.status}: {text[:200]}")
            data = await resp.json()
            content = data["choices"][0]["message"]["content"]
            return self._parse_response(content)

    async def _call_anthropic(self, user_msg: str) -> EscalationResult:
        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": LLM_MODEL,
            "max_tokens": 500,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_msg}],
            "temperature": 0.3,
        }
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with self._session.post(url, json=payload, headers=headers, timeout=30) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Anthropic HTTP {resp.status}: {text[:200]}")
            data = await resp.json()
            content = data["content"][0]["text"]
            return self._parse_response(content)

    def _parse_response(self, content: str) -> EscalationResult:
        """Parse LLM JSON response into EscalationResult."""
        try:
            # Strip markdown code fences if present
            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                cleaned = cleaned.rsplit("```", 1)[0]
            obj = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response as JSON: {content[:200]}")
            return EscalationResult(
                verdict=EscalationVerdict.WATCH,
                level="NORMAL",
                reason="LLM応答の解析に失敗。経過観察します。",
                message="",
                raw_response=content,
            )

        verdict = obj.get("verdict", "WATCH").upper()
        if verdict not in (EscalationVerdict.NOTIFY, EscalationVerdict.WATCH, EscalationVerdict.IGNORE):
            verdict = EscalationVerdict.WATCH

        level = obj.get("level", "NORMAL").upper()
        if level not in ("CRITICAL", "HIGH", "NORMAL"):
            level = "NORMAL"

        return EscalationResult(
            verdict=verdict,
            level=level,
            reason=obj.get("reason", ""),
            message=obj.get("message", ""),
            raw_response=content,
        )

    def _reset_daily_if_needed(self):
        today = date.today()
        if self._daily_date != today:
            self._daily_date = today
            self._daily_calls = 0

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
