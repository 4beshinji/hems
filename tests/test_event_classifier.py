"""Tests for brain EventClassifier (P3)."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock


@dataclass
class _StubEvent:
    id: str
    title: str
    description: str = ""
    location: str = ""
    start_ts: float = 0.0


class TestEventPlan:
    def test_json_roundtrip(self):
        from annotator import EventPlan

        plan = EventPlan(
            lead_time_min=45,
            needs_pre_event=True,
            priority=2,
            context_hint="meeting",
        )
        raw = plan.to_json()
        restored = EventPlan.from_json(raw)
        assert restored.lead_time_min == 45
        assert restored.needs_pre_event is True
        assert restored.priority == 2
        assert restored.context_hint == "meeting"

    def test_from_json_clamps_out_of_range(self):
        from annotator import EventPlan

        wild = '{"lead_time_min": 9999, "needs_pre_event": true, "priority": 99, "context_hint": null}'
        plan = EventPlan.from_json(wild)
        assert plan.lead_time_min == 120  # clamped upper
        assert plan.priority == 5  # clamped upper
        assert plan.context_hint is None

    def test_from_json_invalid_returns_defaults(self):
        from annotator import EventPlan

        plan = EventPlan.from_json("not valid json at all")
        assert plan.lead_time_min == 30
        assert plan.needs_pre_event is True


class TestEventClassifier:
    def test_plan_event_without_llm_returns_default(self):
        from annotator import EventClassifier

        clf = EventClassifier(llm_router=None)
        plan = asyncio.run(clf.plan_event(_StubEvent(id="x", title="会議")))
        assert plan.lead_time_min == 30
        assert plan.needs_pre_event is True

    def test_plan_event_empty_title(self):
        from annotator import EventClassifier

        clf = EventClassifier(llm_router=None)
        plan = asyncio.run(clf.plan_event(_StubEvent(id="x", title="")))
        assert plan.lead_time_min == 30

    def test_plan_event_uses_llm(self):
        from annotator import EventClassifier

        llm = AsyncMock()
        llm.chat = AsyncMock(
            return_value=MagicMock(
                content='{"lead_time_min": 45, "needs_pre_event": true, "priority": 1, "context_hint": "doctor_visit"}'
            )
        )
        clf = EventClassifier(llm_router=llm)
        plan = asyncio.run(clf.plan_event(_StubEvent(id="e", title="歯科予約")))
        assert plan.lead_time_min == 45
        assert plan.priority == 1
        assert plan.context_hint == "doctor_visit"
        llm.chat.assert_awaited_once()

    def test_plan_event_strips_markdown_fences(self):
        from annotator import EventClassifier

        llm = AsyncMock()
        llm.chat = AsyncMock(
            return_value=MagicMock(
                content='```json\n{"lead_time_min": 20, "needs_pre_event": true, '
                '"priority": 3, "context_hint": "commute"}\n```'
            )
        )
        clf = EventClassifier(llm_router=llm)
        plan = asyncio.run(clf.plan_event(_StubEvent(id="e", title="電車")))
        assert plan.lead_time_min == 20

    def test_plan_event_llm_exception_returns_default(self):
        from annotator import EventClassifier

        llm = AsyncMock()
        llm.chat = AsyncMock(side_effect=RuntimeError("boom"))
        clf = EventClassifier(llm_router=llm)
        plan = asyncio.run(clf.plan_event(_StubEvent(id="e", title="謎")))
        assert plan.lead_time_min == 30

    def test_second_call_hits_cache(self):
        """The second lookup (memory L1) must NOT re-invoke the LLM."""
        from annotator import ClassifierCache, EventClassifier

        llm = AsyncMock()
        llm.chat = AsyncMock(
            return_value=MagicMock(
                content='{"lead_time_min": 45, "needs_pre_event": true, "priority": 2, "context_hint": null}'
            )
        )
        cache = ClassifierCache()  # memory-only
        clf = EventClassifier(llm_router=llm, cache=cache)
        ev = _StubEvent(id="e", title="同じ予定")

        asyncio.run(clf.plan_event(ev))
        asyncio.run(clf.plan_event(ev))
        assert llm.chat.await_count == 1
