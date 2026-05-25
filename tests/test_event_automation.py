"""
Tests for EventAutomation — wake_up routing, boot_load_used branch,
weather_report fallback, news_briefing staleness refresh, daily debounce.
"""

import asyncio
import importlib
import time
from datetime import datetime
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def ea_mod(monkeypatch):
    monkeypatch.setenv("NEWS_BRIDGE_URL", "http://news-bridge:8000")
    monkeypatch.setenv("NEWS_REFRESH_STALE_HOURS", "2")
    import event_automation

    importlib.reload(event_automation)
    return event_automation


class _AsyncCtx:
    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = payload or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._payload


class StubSession:
    """aiohttp.ClientSession-shaped stub recording every request."""

    def __init__(self, *, get_responses=None, post_responses=None):
        self.gets: list[tuple[str, dict]] = []
        self.posts: list[tuple[str, dict]] = []
        self._get_responses = get_responses or {}
        self._post_responses = post_responses or {}

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        match = next((v for k, v in self._get_responses.items() if k in url), None)
        return match if match else _AsyncCtx(404)

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        match = next((v for k, v in self._post_responses.items() if k in url), None)
        return match if match else _AsyncCtx(200, {})


class StubToolExecutor:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, tool_name, args):
        self.calls.append((tool_name, args))
        return {"success": True}


def _make_world_model(*, weather_loaded=True, news_age_hours=0.0):
    """Build a real WorldModel — catches attribute path drifts that MagicMock
    silently allows."""
    from world_model import WorldModel

    wm = WorldModel()
    w = wm.physical.weather
    if weather_loaded:
        w.last_update = time.time()
        w.condition = "晴れ"
        w.temperature = 20
        w.humidity = 50
    # forecast / alerts default to []

    ns = wm.digital.news_state
    ns.daily_chunks = ["news A", "news B"]
    ns.daily_timestamp = time.time() - news_age_hours * 3600
    return wm


class TestWakeUpRouting:
    def test_boot_load_used_skips_voice_actions(self, ea_mod):
        wm = _make_world_model()
        te = StubToolExecutor()

        # boot_load_manager that is_ready and has a cache to play
        cache = MagicMock()
        cache.briefing_chunks = ["chunk1"]
        cache.audio_urls = []  # forces speak() fallback in _execute_boot_load_briefing
        blm = MagicMock()
        blm.is_ready = True
        blm.cache = cache
        blm.reset = MagicMock()

        ea = ea_mod.EventAutomation(
            tool_executor=te,
            world_model=wm,
            llm_client=None,
            character=None,
            boot_load_manager=blm,
        )

        async def run():
            await ea.trigger("wake_up")

        asyncio.run(run())

        # boot_load played its single chunk via speak()
        speak_calls = [c for c in te.calls if c[0] == "speak"]
        # 1 from boot_load briefing playback. morning_greeting / news_briefing
        # / weather_report should NOT have added more calls (they're skipped
        # when boot_load_used).
        assert len(speak_calls) == 1
        assert "chunk1" in speak_calls[0][1]["message"]
        blm.reset.assert_called_once()

    def test_no_boot_load_runs_all_actions(self, ea_mod):
        wm = _make_world_model(weather_loaded=True, news_age_hours=0.5)
        te = StubToolExecutor()

        # Stub LLM that returns a short greeting
        async def greet(*a, **kw):
            r = MagicMock()
            r.error = None
            r.content = "おはよう。"
            return r

        llm = MagicMock()
        llm.chat = greet

        # News bridge returns chunks for news_briefing
        session = StubSession(
            get_responses={"/api/news/latest": _AsyncCtx(200, {"chunks": ["headline"]})},
        )

        blm = MagicMock()
        blm.is_ready = False

        ea = ea_mod.EventAutomation(
            tool_executor=te,
            world_model=wm,
            llm_client=llm,
            character=None,
            boot_load_manager=blm,
        )
        ea.set_session(session)

        async def run():
            await ea.trigger("wake_up")

        asyncio.run(run())
        speak_calls = [c for c in te.calls if c[0] == "speak"]
        # Expect: morning_greeting (1) + news intro (1) + news headline (1) + weather (1)
        assert len(speak_calls) >= 3
        messages = " ".join(c[1]["message"] for c in speak_calls)
        assert "おはよう" in messages
        assert "ニュース" in messages
        assert "晴れ" in messages

    def test_daily_debounce_skips_second_fire(self, ea_mod):
        wm = _make_world_model()
        te = StubToolExecutor()
        blm = MagicMock()
        blm.is_ready = False

        ea = ea_mod.EventAutomation(
            tool_executor=te,
            world_model=wm,
            boot_load_manager=blm,
        )
        ea.set_session(StubSession())

        async def run():
            await ea.trigger("wake_up")
            calls_after_first = len(te.calls)
            await ea.trigger("wake_up")
            return calls_after_first, len(te.calls)

        first, second = asyncio.run(run())
        # Second call should not add tool calls (silently skipped)
        assert second == first


class TestWeatherReportFallback:
    def test_speaks_apology_when_data_missing(self, ea_mod):
        wm = _make_world_model(weather_loaded=False)
        te = StubToolExecutor()
        ea = ea_mod.EventAutomation(tool_executor=te, world_model=wm)

        async def run():
            await ea._action_weather_report()

        asyncio.run(run())
        speak_calls = [c for c in te.calls if c[0] == "speak"]
        assert len(speak_calls) == 1
        assert "天気情報" in speak_calls[0][1]["message"]

    def test_speaks_summary_when_data_present(self, ea_mod):
        wm = _make_world_model(weather_loaded=True)
        te = StubToolExecutor()
        ea = ea_mod.EventAutomation(tool_executor=te, world_model=wm)

        async def run():
            await ea._action_weather_report()

        asyncio.run(run())
        msg = te.calls[0][1]["message"]
        assert "晴れ" in msg
        assert "20" in msg


class TestNewsBriefingRefresh:
    def test_stale_cache_triggers_refresh(self, ea_mod):
        wm = _make_world_model(news_age_hours=5)  # well beyond 2h threshold
        te = StubToolExecutor()
        session = StubSession(
            get_responses={"/api/news/latest": _AsyncCtx(200, {"chunks": ["fresh news"]})},
            post_responses={"/api/news/refresh": _AsyncCtx(200, {})},
        )

        ea = ea_mod.EventAutomation(tool_executor=te, world_model=wm)
        ea.set_session(session)

        async def run():
            await ea._action_news_briefing()

        asyncio.run(run())
        # refresh POST happened
        assert any("/api/news/refresh" in url for url, _ in session.posts)

    def test_fresh_cache_skips_refresh(self, ea_mod):
        wm = _make_world_model(news_age_hours=0.1)  # 6 minutes old, fresh
        te = StubToolExecutor()
        session = StubSession(
            get_responses={"/api/news/latest": _AsyncCtx(200, {"chunks": ["headline"]})},
        )

        ea = ea_mod.EventAutomation(tool_executor=te, world_model=wm)
        ea.set_session(session)

        async def run():
            await ea._action_news_briefing()

        asyncio.run(run())
        # No refresh was triggered
        assert not any("/api/news/refresh" in url for url, _ in session.posts)


class TestScheduledEvents:
    def test_check_scheduled_fires_at_target_time(self, ea_mod, monkeypatch):
        wm = _make_world_model()
        te = StubToolExecutor()
        ea = ea_mod.EventAutomation(tool_executor=te, world_model=wm)
        ea.set_session(StubSession())

        # Replace automations: a scheduled noon weather report
        ea.automations = [{"event": "scheduled", "time": "12:00", "actions": ["weather_report"]}]

        # Pretend now is 12:00 exactly
        fake_now = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)

        class _FakeDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return fake_now

        monkeypatch.setattr(ea_mod, "datetime", _FakeDT)

        async def run():
            await ea.check_scheduled()

        asyncio.run(run())
        speak_calls = [c for c in te.calls if c[0] == "speak"]
        assert len(speak_calls) >= 1

    def test_check_scheduled_does_not_fire_outside_target_time(self, ea_mod, monkeypatch):
        wm = _make_world_model()
        te = StubToolExecutor()
        ea = ea_mod.EventAutomation(tool_executor=te, world_model=wm)
        ea.automations = [{"event": "scheduled", "time": "12:00", "actions": ["weather_report"]}]

        fake_now = datetime.now().replace(hour=11, minute=30, second=0, microsecond=0)

        class _FakeDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return fake_now

        monkeypatch.setattr(ea_mod, "datetime", _FakeDT)

        async def run():
            await ea.check_scheduled()

        asyncio.run(run())
        assert te.calls == []
