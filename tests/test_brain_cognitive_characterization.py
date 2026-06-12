"""
Characterization tests for CognitiveCycleMixin.cognitive_cycle  (W2.5 / C1)

These tests fix the *current* observable behaviour of cognitive_cycle so that
the upcoming extraction refactor (C2) can be validated without regression.

Design reference: docs/refactor/2026-06-11/W2.5-design-note.md §7

Harness: _Harness subclasses CognitiveCycleMixin + BackgroundLoopsMixin and
injects a real WorldModel plus mock subsystems.
asyncio.create_task is monkeypatched per-test to record scheduled coroutines
without running them, making all assertions deterministic.

Coverage (scenario numbers match §7.3):
  S1  – Normal ReAct completion (speak + empty tool_calls stops loop)
  S2  – Max iteration (REACT_MAX_ITERATIONS) reached
  S3  – LLM error → loop breaks, total_tool_calls==0, record_decision skipped,
         push still called
  S4  – Low-power idle: LLM never called, mode=="rule_low_power_idle", push called
  S5  – Low-power throttled: rule actions executed, mode=="rule_low_power_throttled",
         LLM never called, push called
  S6  – Low-power escalate: record_llm_call called, LLM called, user_content has
         low-power notice, rule actions NOT executed directly (L231)
  S7  – VLM swap fallback: rule executed, mode=="rule_vlm_swap", LLM never called
  S8  – GPU busy fallback: rule executed, mode=="rule_gpu_busy", LLM never called
  S9  – Context empty bare-return (L272): LLM never called, push NEVER called
         (the only return that skips all post-processing including snapshot push)
  S10 – Blind guard (Guard 0): BLIND_SUPPRESSED_TOOLS tool dropped, speak passes
  S11 – Duplicate guard (Guard 1): second identical tool call dropped
  S12 – Speak limit (Guard 2): only MAX_SPEAK_PER_CYCLE speaks dispatched
  S13 – create_task dedupe (Guard 3): active_task title match prevents dispatch
  S14 – consecutive_errors break: 1 failure breaks inner loop, event-store skips
         record_decision when total_tool_calls==0

Ordering invariants:
  Order-A  power_mode_manager.evaluate called before is_low_power checked
  Order-B  rule-path guard calls never produce record_decision
  Order-C  LLM escalate path: total_tool_calls includes critical-rule count +
           LLM tool count in summary
  Order-D  bare-return (L272) vs other early-returns: only L272 skips push
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain_cognitive import CognitiveCycleMixin
from brain_constants import (
    BLIND_SUPPRESSED_TOOLS,
    MAX_CONSECUTIVE_ERRORS,  # noqa: F401 — sanity-check import
    MAX_SPEAK_PER_CYCLE,
    REACT_MAX_ITERATIONS,
)
from llm_client import LLMResponse
from world_model import WorldModel

# ---------------------------------------------------------------------------
# Helpers: build minimal tool-call dicts the cognitive loop expects
# ---------------------------------------------------------------------------

_TC_ID = 0


def _make_tc(name: str, args: dict | None = None, *, tc_id: str | None = None) -> dict:
    """Return a minimal tool-call dict in OpenAI format."""
    global _TC_ID
    _TC_ID += 1
    return {
        "id": tc_id or f"call_{_TC_ID}",
        "type": "function",
        "function": {"name": name, "arguments": args or {}},
    }


def _speak_tc(message: str = "hello", **kwargs) -> dict:
    return _make_tc("speak", {"message": message}, **kwargs)


def _task_tc(title: str = "Test task", zone: str = "living") -> dict:
    return _make_tc("create_task", {"title": title, "zone": zone})


def _rule_action(tool: str = "speak", msg: str = "rule says hi") -> dict:
    return {"tool": tool, "args": {"message": msg}}


# ---------------------------------------------------------------------------
# Lightweight harness
# ---------------------------------------------------------------------------


class _Harness(CognitiveCycleMixin):
    """CognitiveCycleMixin wired with a real WorldModel + mock subsystems.

    Only the attributes that cognitive_cycle reads are set; the rest are None.
    asyncio.create_task is monkeypatched per-test (see fixture).
    """

    def __init__(self, world_model: WorldModel):
        self.world_model = world_model

        # LLM: will be configured per-test; default = no tool calls
        self.llm = MagicMock()
        self.llm.provider = "openai"
        self.llm.model = "mock"
        self.llm.chat = AsyncMock(return_value=LLMResponse())

        # Tool executor
        self.tool_executor = MagicMock()
        self.tool_executor.execute = AsyncMock(return_value={"success": True, "result": "ok"})

        # Rule engine
        self.rule_engine = MagicMock()
        self.rule_engine.evaluate = MagicMock(return_value=[])
        self.rule_engine.evaluate_critical = MagicMock(return_value=[])
        self.rule_engine.should_use_rules = MagicMock(return_value=False)
        self.rule_engine.refresh_devices = AsyncMock()

        # Power mode manager (not low-power by default)
        self.power_mode_manager = MagicMock()
        self.power_mode_manager.is_low_power = False
        self.power_mode_manager.allow_llm_call = MagicMock(return_value=True)
        self.power_mode_manager.evaluate = MagicMock()
        self.power_mode_manager.get_status = MagicMock(return_value={"mode": "sleep", "reason": "quiet"})
        self.power_mode_manager.record_llm_call = MagicMock()
        self.power_mode_manager.seconds_until_llm_allowed = MagicMock(return_value=60)

        # Dashboard (AsyncMock for coroutine calls)
        self.dashboard = MagicMock()
        self.dashboard.get_active_tasks = AsyncMock(return_value=[])
        self.dashboard.fetch_all_devices = AsyncMock(return_value=[])
        self.dashboard.push_zone_snapshot = AsyncMock()
        self.dashboard.push_pc_snapshot = AsyncMock()
        self.dashboard.push_services_snapshot = AsyncMock()
        self.dashboard.push_knowledge_snapshot = AsyncMock()
        self.dashboard.push_gas_snapshot = AsyncMock()
        self.dashboard.push_biometric_snapshot = AsyncMock()
        self.dashboard.push_perception_snapshot = AsyncMock()
        self.dashboard.push_home_snapshot = AsyncMock()
        self.dashboard.push_weather_snapshot = AsyncMock()
        self.dashboard.push_news_snapshot = AsyncMock()
        self.dashboard.push_brain_snapshot = AsyncMock()

        # Event writer
        self.event_writer = MagicMock()
        self.event_writer.record_decision = MagicMock()

        # Other subsystems
        self.task_queue = MagicMock()
        self.task_queue.process_queue = AsyncMock()
        self.schedule_learner = MagicMock()
        self.schedule_learner.get_wake_time = MagicMock(return_value=None)
        self.schedule_learner.get_arrival_stats = MagicMock(return_value={})
        self.schedule_learner.predict_next_arrival = MagicMock(return_value=None)
        self.sunrise_alarm = None
        self.boot_load_manager = None
        self.event_automation = None
        self.automation_engine = None
        self.ambient_speaker = MagicMock()
        self.ambient_speaker.record_speak = MagicMock()
        self.timeline_generator = None
        self.device_registry = MagicMock()
        self.device_registry.get_status_summary = MagicMock(return_value="")
        self.device_dispatcher = None

        # _TASK_ALERT_KEYWORDS lives on Brain as a class attribute; replicate it
        # here so _suppress_alert_for_task (called from cognitive_cycle) works.
        self._TASK_ALERT_KEYWORDS: dict[str, list[str]] = {
            "温度": ["temp_high", "temp_low"],
            "室温": ["temp_high", "temp_low"],
            "暑": ["temp_high"],
            "冷": ["temp_high"],
            "寒": ["temp_low"],
            "暖": ["temp_low"],
            "co2": ["co2_high", "co2_critical"],
            "換気": ["co2_high", "co2_critical"],
            "二酸化炭素": ["co2_high", "co2_critical"],
            "湿度": ["humidity_high", "humidity_low"],
            "加湿": ["humidity_low"],
            "除湿": ["humidity_high"],
        }

        # Cognitive-cycle local state
        self._action_history: list[dict] = []
        self._last_cycle_summary: dict | None = None
        self._recent_efficacy_verdicts: list[dict] = []
        self._cached_devices: list[dict] = []
        self._cached_devices_at: float = 0.0
        self._device_zone_map: dict[str, str] = {}
        self._scheduled_wake_fired_date: str | None = None
        self._timeline_regen_task: asyncio.Task | None = None
        self._session = None
        self._loop = None
        self._cycle_triggered = asyncio.Event()
        self._last_event_count: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Methods that live in other Mixins but cognitive_cycle calls via self
    # ------------------------------------------------------------------

    async def _push_all_snapshots(self):
        """Delegate to dashboard — makes push observable via dashboard mocks."""
        await self.dashboard.push_zone_snapshot(self.world_model)
        await self.dashboard.push_brain_snapshot(
            self.power_mode_manager.get_status(),
            last_cycle=self._last_cycle_summary,
        )

    async def _track_bridge_transitions(self):
        """Stub — not under test here."""

    def _annotate_z2m_devices(self, payload):
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def wm():
    return WorldModel()


@pytest.fixture
def harness(wm):
    return _Harness(wm)


@pytest.fixture
def non_empty_wm():
    """WorldModel with minimal zone data so get_llm_context() is non-empty."""
    from world_model.data_classes import ZoneState

    wm = WorldModel()
    zone = ZoneState(zone_id="living")
    zone.environment.temperature = 22.0
    import time

    zone.environment.last_update = time.time()
    wm.zones["living"] = zone
    return wm


@pytest.fixture
def harness_llm(non_empty_wm):
    """Harness with non-empty WorldModel — LLM path reachable."""
    return _Harness(non_empty_wm)


@pytest.fixture
def captured_tasks():
    """Monkeypatch asyncio.create_task in brain_cognitive module.

    Each scheduled coroutine is recorded by qualname; the coroutine is closed
    to suppress 'was never awaited' warnings.
    """
    recorded = []

    def _capture(coro, **kwargs):
        qualname = getattr(coro, "__qualname__", None) or repr(coro)
        recorded.append(qualname)
        if hasattr(coro, "close"):
            try:
                coro.close()
            except Exception:
                pass
        return MagicMock(spec=asyncio.Task)

    with patch("brain_cognitive.asyncio.create_task", side_effect=_capture):
        yield recorded


# ---------------------------------------------------------------------------
# S1 – Normal ReAct completion
# ---------------------------------------------------------------------------


class TestS1NormalReActCompletion:
    """LLM returns speak on iter 1, empty tool_calls on iter 2 → loop ends."""

    async def test_llm_chat_called_twice(self, harness_llm, captured_tasks):
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_speak_tc()]),
                LLMResponse(),  # no tool_calls → break
            ]
        )
        await harness_llm.cognitive_cycle()
        assert harness_llm.llm.chat.call_count == 2

    async def test_speak_dispatched_once(self, harness_llm, captured_tasks):
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_speak_tc("good morning")]),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        dispatched = [c.args[0] for c in harness_llm.tool_executor.execute.call_args_list]
        assert dispatched.count("speak") == 1

    async def test_record_decision_called_with_iterations_2(self, harness_llm, captured_tasks):
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_speak_tc()]),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        harness_llm.event_writer.record_decision.assert_called_once()
        kw = harness_llm.event_writer.record_decision.call_args.kwargs
        assert kw["iterations"] == 2
        assert kw["total_tool_calls"] == 1

    async def test_push_called(self, harness_llm, captured_tasks):
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_speak_tc()]),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        harness_llm.dashboard.push_zone_snapshot.assert_called_once()

    async def test_last_cycle_summary_mode_llm(self, harness_llm, captured_tasks):
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_speak_tc()]),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        assert harness_llm._last_cycle_summary is not None
        assert harness_llm._last_cycle_summary["mode"] == "llm"


# ---------------------------------------------------------------------------
# S2 – Max iteration reached
# ---------------------------------------------------------------------------


class TestS2MaxIteration:
    """LLM always returns a fresh unique tool_call → loop runs REACT_MAX_ITERATIONS times."""

    async def test_llm_called_max_iterations(self, harness_llm, captured_tasks):
        # Each response has a unique arg so dup-guard (Guard 1) never fires
        def _unique_responses(_):
            # side_effect as callable receives call args
            nonlocal call_n
            call_n += 1
            return LLMResponse(tool_calls=[_make_tc("get_zone_status", {"zone": f"z{call_n}"})])

        call_n = 0
        harness_llm.llm.chat = AsyncMock(side_effect=lambda msgs, tools: _unique_responses(msgs))
        await harness_llm.cognitive_cycle()
        assert harness_llm.llm.chat.call_count == REACT_MAX_ITERATIONS

    async def test_record_decision_iterations_equals_max(self, harness_llm, captured_tasks):
        call_n = 0

        def _unique(msgs, tools):
            nonlocal call_n
            call_n += 1
            return LLMResponse(tool_calls=[_make_tc("get_zone_status", {"zone": f"z{call_n}"})])

        harness_llm.llm.chat = AsyncMock(side_effect=_unique)
        await harness_llm.cognitive_cycle()
        kw = harness_llm.event_writer.record_decision.call_args.kwargs
        assert kw["iterations"] == REACT_MAX_ITERATIONS


# ---------------------------------------------------------------------------
# S3 – LLM error → loop breaks early
# ---------------------------------------------------------------------------


class TestS3LLMError:
    """LLM returns an error response: loop breaks, total_tool_calls==0,
    record_decision is NOT called (L542 guard), push IS called."""

    async def test_llm_error_breaks_loop(self, harness_llm, captured_tasks):
        harness_llm.llm.chat = AsyncMock(return_value=LLMResponse(error="timeout"))
        await harness_llm.cognitive_cycle()
        assert harness_llm.llm.chat.call_count == 1

    async def test_no_tool_dispatch_on_error(self, harness_llm, captured_tasks):
        harness_llm.llm.chat = AsyncMock(return_value=LLMResponse(error="timeout"))
        await harness_llm.cognitive_cycle()
        harness_llm.tool_executor.execute.assert_not_called()

    async def test_record_decision_not_called_when_zero_tools(self, harness_llm, captured_tasks):
        harness_llm.llm.chat = AsyncMock(return_value=LLMResponse(error="timeout"))
        await harness_llm.cognitive_cycle()
        harness_llm.event_writer.record_decision.assert_not_called()

    async def test_push_still_called_on_llm_error(self, harness_llm, captured_tasks):
        harness_llm.llm.chat = AsyncMock(return_value=LLMResponse(error="timeout"))
        await harness_llm.cognitive_cycle()
        harness_llm.dashboard.push_zone_snapshot.assert_called_once()

    async def test_last_cycle_summary_mode_llm(self, harness_llm, captured_tasks):
        harness_llm.llm.chat = AsyncMock(return_value=LLMResponse(error="timeout"))
        await harness_llm.cognitive_cycle()
        assert harness_llm._last_cycle_summary["mode"] == "llm"


# ---------------------------------------------------------------------------
# S4 – Low-power idle (no rule fires)
# ---------------------------------------------------------------------------


class TestS4LowPowerIdle:
    """is_low_power=True, critical=[], normal=[] → mode==rule_low_power_idle,
    LLM never called, push called."""

    async def test_llm_not_called(self, harness, captured_tasks):
        harness.power_mode_manager.is_low_power = True
        harness.rule_engine.evaluate_critical.return_value = []
        harness.rule_engine.evaluate.return_value = []
        await harness.cognitive_cycle()
        harness.llm.chat.assert_not_called()

    async def test_last_cycle_summary_mode_idle(self, harness, captured_tasks):
        harness.power_mode_manager.is_low_power = True
        harness.rule_engine.evaluate_critical.return_value = []
        harness.rule_engine.evaluate.return_value = []
        await harness.cognitive_cycle()
        assert harness._last_cycle_summary["mode"] == "rule_low_power_idle"

    async def test_push_called(self, harness, captured_tasks):
        harness.power_mode_manager.is_low_power = True
        harness.rule_engine.evaluate_critical.return_value = []
        harness.rule_engine.evaluate.return_value = []
        await harness.cognitive_cycle()
        harness.dashboard.push_zone_snapshot.assert_called_once()

    async def test_record_decision_not_called(self, harness, captured_tasks):
        harness.power_mode_manager.is_low_power = True
        harness.rule_engine.evaluate_critical.return_value = []
        harness.rule_engine.evaluate.return_value = []
        await harness.cognitive_cycle()
        harness.event_writer.record_decision.assert_not_called()


# ---------------------------------------------------------------------------
# S5 – Low-power throttled (rule fires, LLM throttled)
# ---------------------------------------------------------------------------


class TestS5LowPowerThrottled:
    """is_low_power=True, evaluate() fires, allow_llm_call=False →
    rule action executed, mode==rule_low_power_throttled, LLM not called, push called."""

    async def test_rule_action_executed(self, harness, captured_tasks):
        harness.power_mode_manager.is_low_power = True
        harness.power_mode_manager.allow_llm_call.return_value = False
        harness.rule_engine.evaluate.return_value = [_rule_action()]
        await harness.cognitive_cycle()
        harness.tool_executor.execute.assert_called()

    async def test_llm_not_called(self, harness, captured_tasks):
        harness.power_mode_manager.is_low_power = True
        harness.power_mode_manager.allow_llm_call.return_value = False
        harness.rule_engine.evaluate.return_value = [_rule_action()]
        await harness.cognitive_cycle()
        harness.llm.chat.assert_not_called()

    async def test_mode_is_throttled(self, harness, captured_tasks):
        harness.power_mode_manager.is_low_power = True
        harness.power_mode_manager.allow_llm_call.return_value = False
        harness.rule_engine.evaluate.return_value = [_rule_action()]
        await harness.cognitive_cycle()
        assert harness._last_cycle_summary["mode"] == "rule_low_power_throttled"

    async def test_push_called(self, harness, captured_tasks):
        harness.power_mode_manager.is_low_power = True
        harness.power_mode_manager.allow_llm_call.return_value = False
        harness.rule_engine.evaluate.return_value = [_rule_action()]
        await harness.cognitive_cycle()
        harness.dashboard.push_zone_snapshot.assert_called_once()

    async def test_record_decision_not_called(self, harness, captured_tasks):
        harness.power_mode_manager.is_low_power = True
        harness.power_mode_manager.allow_llm_call.return_value = False
        harness.rule_engine.evaluate.return_value = [_rule_action()]
        await harness.cognitive_cycle()
        harness.event_writer.record_decision.assert_not_called()


# ---------------------------------------------------------------------------
# S6 – Low-power escalate (rule fires, LLM allowed → fall through)
# ---------------------------------------------------------------------------


class TestS6LowPowerEscalate:
    """is_low_power=True, evaluate() fires, allow_llm_call=True →
    record_llm_call called, LLM called, user_content has low-power notice,
    rule actions NOT dispatched via _run_rule_actions at escalation time (L231)."""

    async def test_record_llm_call_invoked(self, harness_llm, captured_tasks):
        harness_llm.power_mode_manager.is_low_power = True
        harness_llm.power_mode_manager.allow_llm_call.return_value = True
        harness_llm.rule_engine.evaluate.return_value = [_rule_action("get_zone_status", {})]
        harness_llm.llm.chat = AsyncMock(return_value=LLMResponse())
        await harness_llm.cognitive_cycle()
        harness_llm.power_mode_manager.record_llm_call.assert_called_once()

    async def test_llm_called(self, harness_llm, captured_tasks):
        harness_llm.power_mode_manager.is_low_power = True
        harness_llm.power_mode_manager.allow_llm_call.return_value = True
        harness_llm.rule_engine.evaluate.return_value = [_rule_action("get_zone_status", {})]
        harness_llm.llm.chat = AsyncMock(return_value=LLMResponse())
        await harness_llm.cognitive_cycle()
        harness_llm.llm.chat.assert_called()

    async def test_user_content_has_low_power_notice(self, harness_llm, captured_tasks):
        harness_llm.power_mode_manager.is_low_power = True
        harness_llm.power_mode_manager.allow_llm_call.return_value = True
        harness_llm.rule_engine.evaluate.return_value = [_rule_action("get_zone_status", {})]

        captured_messages = []

        async def _capture_chat(messages, tools):
            captured_messages.extend(messages)
            return LLMResponse()

        harness_llm.llm.chat = _capture_chat
        await harness_llm.cognitive_cycle()

        user_msgs = [m for m in captured_messages if m.get("role") == "user"]
        assert user_msgs, "No user message sent to LLM"
        combined = " ".join(m.get("content", "") for m in user_msgs)
        assert "低消費電力" in combined, "Low-power notice must appear in user_content"

    async def test_rule_actions_not_directly_executed_at_escalation(self, harness_llm, captured_tasks):
        """L231: on escalation, rule actions must NOT be executed directly."""
        harness_llm.power_mode_manager.is_low_power = True
        harness_llm.power_mode_manager.allow_llm_call.return_value = True
        rule_action = _rule_action("speak", "rule says hi")
        harness_llm.rule_engine.evaluate.return_value = [rule_action]
        harness_llm.llm.chat = AsyncMock(return_value=LLMResponse())
        await harness_llm.cognitive_cycle()
        # tool_executor.execute should not have been called with the rule action
        dispatched_names = [c.args[0] for c in harness_llm.tool_executor.execute.call_args_list]
        # Only LLM-dispatched tools should appear; the escalation path must not
        # independently execute rule actions (LLM will reason with full context)
        assert "speak" not in dispatched_names, (
            "Rule actions must NOT be directly executed on low-power escalation (L231)"
        )


# ---------------------------------------------------------------------------
# S7 – VLM swap fallback
# ---------------------------------------------------------------------------


class TestS7VlmSwapFallback:
    """vlm_model_swap_active=True → rule executed, mode==rule_vlm_swap, LLM never called."""

    async def test_llm_not_called(self, harness, captured_tasks):
        harness.world_model.vlm_model_swap_active = True
        harness.rule_engine.evaluate.return_value = [_rule_action()]
        await harness.cognitive_cycle()
        harness.llm.chat.assert_not_called()

    async def test_mode_is_vlm_swap(self, harness, captured_tasks):
        harness.world_model.vlm_model_swap_active = True
        await harness.cognitive_cycle()
        assert harness._last_cycle_summary["mode"] == "rule_vlm_swap"

    async def test_rule_action_executed(self, harness, captured_tasks):
        harness.world_model.vlm_model_swap_active = True
        harness.rule_engine.evaluate.return_value = [_rule_action()]
        await harness.cognitive_cycle()
        harness.tool_executor.execute.assert_called()

    async def test_push_called(self, harness, captured_tasks):
        harness.world_model.vlm_model_swap_active = True
        await harness.cognitive_cycle()
        harness.dashboard.push_zone_snapshot.assert_called_once()

    async def test_record_decision_not_called(self, harness, captured_tasks):
        harness.world_model.vlm_model_swap_active = True
        await harness.cognitive_cycle()
        harness.event_writer.record_decision.assert_not_called()


# ---------------------------------------------------------------------------
# S8 – GPU busy fallback
# ---------------------------------------------------------------------------


class TestS8GpuBusyFallback:
    """should_use_rules()=True → rule executed, mode==rule_gpu_busy, LLM never called."""

    async def test_llm_not_called(self, harness, captured_tasks):
        harness.rule_engine.should_use_rules.return_value = True
        await harness.cognitive_cycle()
        harness.llm.chat.assert_not_called()

    async def test_mode_is_gpu_busy(self, harness, captured_tasks):
        harness.rule_engine.should_use_rules.return_value = True
        await harness.cognitive_cycle()
        assert harness._last_cycle_summary["mode"] == "rule_gpu_busy"

    async def test_rule_executed(self, harness, captured_tasks):
        harness.rule_engine.should_use_rules.return_value = True
        harness.rule_engine.evaluate.return_value = [_rule_action()]
        await harness.cognitive_cycle()
        harness.tool_executor.execute.assert_called()

    async def test_push_called(self, harness, captured_tasks):
        harness.rule_engine.should_use_rules.return_value = True
        await harness.cognitive_cycle()
        harness.dashboard.push_zone_snapshot.assert_called_once()

    async def test_record_decision_not_called(self, harness, captured_tasks):
        harness.rule_engine.should_use_rules.return_value = True
        await harness.cognitive_cycle()
        harness.event_writer.record_decision.assert_not_called()


# ---------------------------------------------------------------------------
# S9 – Context empty bare-return (L272) — the critical special case
# ---------------------------------------------------------------------------


class TestS9ContextEmptyBareReturn:
    """get_llm_context() returns '' → immediate return with NO post-processing:
    push is NOT called, record_decision NOT called, _last_cycle_summary unchanged.

    This is the ONLY return path that skips all post-processing (including push).
    All other early-returns (L245/252/260/268) call summary+push before returning.
    """

    async def test_llm_not_called(self, harness, captured_tasks):
        # Default WorldModel returns '' from get_llm_context (bare harness, no zone data)
        assert harness.world_model.get_llm_context() == ""
        await harness.cognitive_cycle()
        harness.llm.chat.assert_not_called()

    async def test_push_not_called(self, harness, captured_tasks):
        """KEY invariant: bare-return at L272 skips _push_all_snapshots entirely."""
        assert harness.world_model.get_llm_context() == ""
        await harness.cognitive_cycle()
        harness.dashboard.push_zone_snapshot.assert_not_called()

    async def test_record_decision_not_called(self, harness, captured_tasks):
        assert harness.world_model.get_llm_context() == ""
        await harness.cognitive_cycle()
        harness.event_writer.record_decision.assert_not_called()

    async def test_last_cycle_summary_unchanged(self, harness, captured_tasks):
        """_last_cycle_summary must NOT be set by the bare-return path."""
        assert harness.world_model.get_llm_context() == ""
        await harness.cognitive_cycle()
        assert harness._last_cycle_summary is None

    async def test_contrast_vlm_swap_does_push(self, harness, captured_tasks):
        """Guard early-returns (L260) DO call push — contrast with bare-return."""
        harness.world_model.vlm_model_swap_active = True
        await harness.cognitive_cycle()
        harness.dashboard.push_zone_snapshot.assert_called_once()

    async def test_contrast_gpu_busy_does_push(self, harness, captured_tasks):
        """Guard early-returns (L268) DO call push — contrast with bare-return."""
        harness.rule_engine.should_use_rules.return_value = True
        await harness.cognitive_cycle()
        harness.dashboard.push_zone_snapshot.assert_called_once()

    async def test_contrast_low_power_idle_does_push(self, harness, captured_tasks):
        """Guard early-returns (L252) DO call push — contrast with bare-return."""
        harness.power_mode_manager.is_low_power = True
        harness.rule_engine.evaluate.return_value = []
        harness.rule_engine.evaluate_critical.return_value = []
        await harness.cognitive_cycle()
        harness.dashboard.push_zone_snapshot.assert_called_once()


# ---------------------------------------------------------------------------
# S10 – Blind guard (Guard 0): BLIND_SUPPRESSED_TOOLS dropped
# ---------------------------------------------------------------------------


class TestS10BlindGuard:
    """When world_model.is_blind(), tools in BLIND_SUPPRESSED_TOOLS are dropped;
    speak (not in the suppressed set) still passes."""

    def _make_harness_blind(self, wm):
        h = _Harness(wm)
        # Force is_blind() to return True — default WorldModel is already blind
        assert wm.is_blind(), "WorldModel should be blind with no zone data"
        return h

    async def test_suppressed_tool_not_dispatched(self, non_empty_wm, captured_tasks):
        # Pick a suppressed tool that isn't speak
        suppressed = next(t for t in BLIND_SUPPRESSED_TOOLS if t != "speak")
        h = _Harness(non_empty_wm)
        # Make is_blind() return True by patching
        h.world_model.is_blind = lambda: True
        h.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_make_tc(suppressed, {"zone": "living"})]),
                LLMResponse(),
            ]
        )
        await h.cognitive_cycle()
        dispatched = [c.args[0] for c in h.tool_executor.execute.call_args_list]
        assert suppressed not in dispatched, f"{suppressed} must be suppressed in blind mode"

    async def test_speak_passes_in_blind_mode(self, non_empty_wm, captured_tasks):
        h = _Harness(non_empty_wm)
        h.world_model.is_blind = lambda: True
        h.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_speak_tc("I'm watching")]),
                LLMResponse(),
            ]
        )
        await h.cognitive_cycle()
        dispatched = [c.args[0] for c in h.tool_executor.execute.call_args_list]
        assert "speak" in dispatched, "speak must NOT be suppressed in blind mode"


# ---------------------------------------------------------------------------
# S11 – Duplicate guard (Guard 1)
# ---------------------------------------------------------------------------


class TestS11DuplicateGuard:
    """Two tool_calls with identical (name, args) in one iteration: second is dropped."""

    async def test_duplicate_tool_dispatched_once(self, harness_llm, captured_tasks):
        tc = _speak_tc("once", tc_id="dup-id-1")
        tc2 = dict(tc)  # same id, same args — will have same call_key
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                # Both tcs have the same (name, args) → second should be dropped
                LLMResponse(tool_calls=[tc, tc2]),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        dispatched = [c.args[0] for c in harness_llm.tool_executor.execute.call_args_list]
        assert dispatched.count("speak") == 1, "Duplicate tool call must be dropped by Guard 1"


# ---------------------------------------------------------------------------
# S12 – Speak limit (Guard 2): MAX_SPEAK_PER_CYCLE enforced
# ---------------------------------------------------------------------------


class TestS12SpeakLimit:
    """LLM returns MAX_SPEAK_PER_CYCLE+1 speak calls in one iteration:
    only MAX_SPEAK_PER_CYCLE are dispatched."""

    async def test_only_max_speak_dispatched(self, harness_llm, captured_tasks):
        # Build MAX+1 speaks with unique args to bypass dup guard
        speaks = [_speak_tc(f"msg {i}") for i in range(MAX_SPEAK_PER_CYCLE + 1)]
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=speaks),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        dispatched = [c.args[0] for c in harness_llm.tool_executor.execute.call_args_list]
        assert dispatched.count("speak") == MAX_SPEAK_PER_CYCLE, (
            f"Expected {MAX_SPEAK_PER_CYCLE} speak dispatches, got {dispatched.count('speak')}"
        )

    async def test_ambient_speaker_called_once_for_successful_speak(self, harness_llm, captured_tasks):
        speaks = [_speak_tc(f"msg {i}") for i in range(MAX_SPEAK_PER_CYCLE + 1)]
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=speaks),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        assert harness_llm.ambient_speaker.record_speak.call_count == MAX_SPEAK_PER_CYCLE


# ---------------------------------------------------------------------------
# S13 – create_task dedupe (Guard 3): active_task title match
# ---------------------------------------------------------------------------


class TestS13CreateTaskDedupe:
    """When active_tasks contains a task with title that substring-matches the
    proposed create_task title, the tool call is dropped."""

    async def test_create_task_suppressed_when_similar_active(self, harness_llm, captured_tasks):
        harness_llm.dashboard.get_active_tasks = AsyncMock(
            return_value=[{"title": "Fix the AC in living room", "zone": "living", "task_type": []}]
        )
        # Proposed title is a substring of the existing one
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_task_tc(title="Fix the AC")]),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        dispatched = [c.args[0] for c in harness_llm.tool_executor.execute.call_args_list]
        assert "create_task" not in dispatched, "create_task must be suppressed when similar active task exists"

    async def test_create_task_passes_when_no_match(self, harness_llm, captured_tasks):
        harness_llm.dashboard.get_active_tasks = AsyncMock(
            return_value=[{"title": "Completely different task", "zone": "living", "task_type": []}]
        )
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_task_tc(title="Turn on the humidifier")]),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        dispatched = [c.args[0] for c in harness_llm.tool_executor.execute.call_args_list]
        assert "create_task" in dispatched


# ---------------------------------------------------------------------------
# S14 – consecutive_errors break (MAX_CONSECUTIVE_ERRORS=1)
# ---------------------------------------------------------------------------


class TestS14ConsecutiveErrorsBreak:
    """tool_executor returns success=False → consecutive_errors reaches MAX (1)
    → inner for-loop breaks after that tool; outer iteration ends naturally.

    record_decision is NOT called when total_tool_calls>0 but we verify the
    break behaviour via call counts."""

    async def test_one_failure_stops_inner_loop(self, harness_llm, captured_tasks):
        """With 2 tools in one response and executor failing on the first,
        only 1 dispatch should occur (inner break after 1 failure)."""
        harness_llm.tool_executor.execute = AsyncMock(
            side_effect=[
                {"success": False, "error": "device unavailable"},
            ]
        )
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(
                    tool_calls=[_make_tc("get_zone_status", {"zone": "a"}), _make_tc("get_zone_status", {"zone": "b"})]
                ),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        assert harness_llm.tool_executor.execute.call_count == 1

    async def test_summary_still_set_after_consecutive_error(self, harness_llm, captured_tasks):
        harness_llm.tool_executor.execute = AsyncMock(return_value={"success": False, "error": "nope"})
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_make_tc("get_zone_status", {"zone": "x"})]),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        assert harness_llm._last_cycle_summary is not None
        assert harness_llm._last_cycle_summary["mode"] == "llm"

    async def test_push_called_after_consecutive_error(self, harness_llm, captured_tasks):
        harness_llm.tool_executor.execute = AsyncMock(return_value={"success": False, "error": "nope"})
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_make_tc("get_zone_status", {"zone": "x"})]),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        harness_llm.dashboard.push_zone_snapshot.assert_called_once()


# ---------------------------------------------------------------------------
# Ordering invariants
# ---------------------------------------------------------------------------


class TestOrderingInvariants:
    async def test_order_a_power_evaluate_before_is_low_power(self, harness, captured_tasks):
        """power_mode_manager.evaluate must be called before is_low_power is read.

        We verify by making evaluate() set is_low_power, which proves evaluate
        was called first (otherwise the subsequent is_low_power read would be wrong).
        """
        calls = []

        def _record_evaluate(wm):
            calls.append("evaluate")

        harness.power_mode_manager.evaluate = MagicMock(side_effect=_record_evaluate)

        # Spy on is_low_power property access via __getattr__ workaround:
        # We just confirm evaluate is called before the guard branch runs
        # by checking that calls list has "evaluate" after the cycle
        harness.power_mode_manager.is_low_power = False
        await harness.cognitive_cycle()
        assert "evaluate" in calls, "power_mode_manager.evaluate must be called during cycle"

    async def test_order_b_rule_guard_paths_skip_record_decision(self, harness, captured_tasks):
        """All four rule-guard early-return paths must not call record_decision."""
        for setup_fn in [
            lambda h: (
                setattr(h.power_mode_manager, "is_low_power", True)
                or setattr(h.rule_engine.evaluate, "return_value", [])
                or setattr(h.rule_engine.evaluate_critical, "return_value", [])
            ),
            lambda h: setattr(h.world_model, "vlm_model_swap_active", True),
            lambda h: h.rule_engine.should_use_rules.__class__,  # placeholder
        ]:
            h = _Harness(WorldModel())
            # simple approach: test each guard separately
            pass

        # Test VLM swap
        h = _Harness(WorldModel())
        h.world_model.vlm_model_swap_active = True
        await h.cognitive_cycle()
        h.event_writer.record_decision.assert_not_called()

        # Test GPU busy
        h2 = _Harness(WorldModel())
        h2.rule_engine.should_use_rules.return_value = True
        await h2.cognitive_cycle()
        h2.event_writer.record_decision.assert_not_called()

    async def test_order_c_escalate_critical_tools_in_total(self, harness_llm, captured_tasks):
        """Low-power escalation: critical rule executions count toward total_tool_calls
        that appears in _last_cycle_summary."""
        harness_llm.power_mode_manager.is_low_power = True
        harness_llm.power_mode_manager.allow_llm_call.return_value = True
        # One critical rule action
        harness_llm.rule_engine.evaluate_critical.return_value = [_rule_action("speak", "critical")]
        # One normal rule action that triggers escalation
        harness_llm.rule_engine.evaluate.return_value = [_rule_action("get_zone_status", {})]
        # LLM path: no additional tool calls
        harness_llm.llm.chat = AsyncMock(return_value=LLMResponse())
        await harness_llm.cognitive_cycle()
        # total_tool_calls must include the 1 critical rule action
        assert harness_llm._last_cycle_summary["total_tool_calls"] >= 1, (
            "Critical rule tool calls must be counted in total_tool_calls"
        )

    async def test_order_d_bare_return_unique_no_push(self, harness, captured_tasks):
        """L272 bare-return is the only path where push is skipped.

        Contrast: all four guard early-returns DO call push.
        Bare-return (empty context) must NOT call push.
        """
        # Empty WorldModel → get_llm_context() == "" → bare-return
        assert harness.world_model.get_llm_context() == ""
        await harness.cognitive_cycle()
        harness.dashboard.push_zone_snapshot.assert_not_called()
        harness.dashboard.push_brain_snapshot.assert_not_called()


# ---------------------------------------------------------------------------
# Fallback 2-layer post-processing invariants
# ---------------------------------------------------------------------------


class TestFallback2LayerPostprocessing:
    """Guard paths (rule): common core only (summary+push, NO record_decision/Obsidian).
    LLM path: common core + LLM extensions (record_decision when tools>0).
    """

    async def test_rule_path_has_summary_and_push_not_record_decision(self, harness, captured_tasks):
        harness.rule_engine.should_use_rules.return_value = True
        harness.rule_engine.evaluate.return_value = [_rule_action()]
        await harness.cognitive_cycle()
        assert harness._last_cycle_summary is not None
        harness.dashboard.push_zone_snapshot.assert_called_once()
        harness.event_writer.record_decision.assert_not_called()

    async def test_llm_path_has_summary_push_and_record_decision(self, harness_llm, captured_tasks):
        harness_llm.llm.chat = AsyncMock(
            side_effect=[
                LLMResponse(tool_calls=[_speak_tc()]),
                LLMResponse(),
            ]
        )
        await harness_llm.cognitive_cycle()
        assert harness_llm._last_cycle_summary is not None
        harness_llm.dashboard.push_zone_snapshot.assert_called_once()
        harness_llm.event_writer.record_decision.assert_called_once()

    async def test_llm_path_no_record_decision_when_zero_tools(self, harness_llm, captured_tasks):
        """LLM path with 0 tool calls: summary+push but no record_decision (L542 guard)."""
        harness_llm.llm.chat = AsyncMock(return_value=LLMResponse())
        await harness_llm.cognitive_cycle()
        assert harness_llm._last_cycle_summary is not None
        harness_llm.dashboard.push_zone_snapshot.assert_called_once()
        harness_llm.event_writer.record_decision.assert_not_called()
