"""Classify a calendar event into a capsule-ready reminder plan.

Output fields:
  lead_time_min   — minutes before start_ts to fire the reminder
  needs_pre_event — whether a pre-event capsule clip should be created at all
  priority        — 1 (high) – 5 (low); affects manifest ordering
  context_hint    — short string for transcript_writer (e.g. "doctor_visit")

Runs only at boot-load time (CapsuleBuilder) so the heavy ``event_classify``
LLM route (``BOOT_LOAD_MODEL``) is acceptable. Results cache to the
``event_lead`` kind.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from .cache import ClassifierCache

if TYPE_CHECKING:
    from llm_router import LLMRouter


DEFAULT_PLAN_LEAD_MIN = 30
DEFAULT_PRIORITY = 3

_SYSTEM = "You classify calendar events for an in-home voice assistant. Output only a compact JSON object, no prose."

_USER_TMPL = (
    "以下のイベントについて、リマインド用のプランを JSON で返してください。\n\n"
    "イベント情報:\n"
    "  タイトル: {title}\n"
    "  説明: {description}\n"
    "  場所: {location}\n\n"
    "返す JSON キー:\n"
    "  lead_time_min   — 何分前に音声リマインドするか (5〜120の整数)\n"
    "  needs_pre_event — そもそもリマインドが必要か (true/false)\n"
    "  priority        — 1=最重要 ... 5=低優先 (整数)\n"
    '  context_hint    — 分類ヒント短い英小文字スネークケース (例: "doctor_visit", "meeting")\n\n'
    '例: {{"lead_time_min": 20, "needs_pre_event": true, "priority": 2, '
    '"context_hint": "meeting"}}'
)


@dataclass
class EventPlan:
    lead_time_min: int = DEFAULT_PLAN_LEAD_MIN
    needs_pre_event: bool = True
    priority: int = DEFAULT_PRIORITY
    context_hint: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "lead_time_min": self.lead_time_min,
                "needs_pre_event": self.needs_pre_event,
                "priority": self.priority,
                "context_hint": self.context_hint,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> EventPlan:
        try:
            d = json.loads(raw)
        except Exception:
            return cls()
        return cls(
            lead_time_min=_clamp(int(d.get("lead_time_min", DEFAULT_PLAN_LEAD_MIN)), 5, 120),
            needs_pre_event=bool(d.get("needs_pre_event", True)),
            priority=_clamp(int(d.get("priority", DEFAULT_PRIORITY)), 1, 5),
            context_hint=d.get("context_hint") or None,
        )


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


class EventClassifier:
    def __init__(
        self,
        *,
        llm_router: LLMRouter | None = None,
        cache: ClassifierCache | None = None,
    ):
        self.llm_router = llm_router
        self.cache = cache or ClassifierCache()

    async def plan_event(self, event) -> EventPlan:
        """Classify one calendar event. Falls back to sensible defaults on any error."""
        title = (getattr(event, "title", "") or "").strip()
        if not title:
            return EventPlan()

        cached = await self.cache.get("event_lead", title)
        if cached is not None:
            return EventPlan.from_json(cached.value)

        if self.llm_router is None:
            return EventPlan()

        plan = await self._llm_plan(event)
        await self.cache.put("event_lead", title, plan.to_json(), "llm")
        return plan

    async def _llm_plan(self, event) -> EventPlan:
        title = getattr(event, "title", "") or ""
        description = getattr(event, "description", "") or ""
        location = getattr(event, "location", "") or ""
        prompt = _USER_TMPL.format(
            title=title,
            description=description or "(なし)",
            location=location or "(なし)",
        )
        try:
            resp = await self.llm_router.chat(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                task_type="event_classify",
                temperature=0.0,
                max_tokens=128,
            )
        except Exception as exc:
            logger.warning("event LLM classify error for {!r}: {}", title, exc)
            return EventPlan()

        content = (getattr(resp, "content", None) or "").strip()
        # Strip markdown fences / stray prose if the model wraps the JSON.
        if "```" in content:
            content = content.split("```")[-2] if content.count("```") >= 2 else content
            content = content.replace("json", "", 1).strip()
        # Locate the JSON object by the first/last braces.
        if "{" in content and "}" in content:
            content = content[content.index("{") : content.rindex("}") + 1]
        return EventPlan.from_json(content)
