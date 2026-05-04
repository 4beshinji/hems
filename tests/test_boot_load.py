"""
Tests for BootLoadManager — state machine, cache persistence, confidence window.
"""

import asyncio
import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _isolated_cache_dir(monkeypatch):
    """Each test gets a clean cache dir so persistence tests don't bleed."""
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("BOOT_LOAD_CACHE_DIR", tmp)
    # Force module reload so the new env var takes effect
    import importlib

    import boot_load_manager

    importlib.reload(boot_load_manager)
    yield boot_load_manager
    # Cleanup
    import shutil

    shutil.rmtree(tmp, ignore_errors=True)


class TestBootLoadStateMachine:
    def test_init_state_is_idle(self, _isolated_cache_dir):
        blm = _isolated_cache_dir.BootLoadManager()
        assert blm.state == _isolated_cache_dir.BootLoadState.IDLE
        assert not blm.is_ready
        assert not blm.is_running

    def test_should_start_false_without_schedule_learner(self, _isolated_cache_dir):
        blm = _isolated_cache_dir.BootLoadManager()
        assert blm.should_start(None) is False

    def test_should_start_false_when_already_run_today(self, _isolated_cache_dir):
        blm = _isolated_cache_dir.BootLoadManager()
        blm._last_run_date = datetime.now().strftime("%Y-%m-%d")
        sl = MagicMock()
        sl.get_wake_time.return_value = time.time() + 1000
        sl.get_wake_confidence.return_value = "high"
        assert blm.should_start(sl) is False

    def test_should_start_true_within_window(self, _isolated_cache_dir):
        blm = _isolated_cache_dir.BootLoadManager()
        sl = MagicMock()
        sl.get_wake_time.return_value = time.time() + 600  # 10 min ahead
        sl.get_wake_confidence.return_value = "high"
        assert blm.should_start(sl) is True

    def test_should_start_false_outside_window(self, _isolated_cache_dir):
        blm = _isolated_cache_dir.BootLoadManager()
        sl = MagicMock()
        sl.get_wake_time.return_value = time.time() + 10000  # ~3h ahead, beyond 45min
        sl.get_wake_confidence.return_value = "high"
        assert blm.should_start(sl) is False


class TestBootLoadConfidenceWindow:
    def test_low_confidence_widens_window(self, _isolated_cache_dir):
        """Low confidence (sparse history) should accept wider lookahead."""
        blm = _isolated_cache_dir.BootLoadManager()
        sl = MagicMock()
        # 70 min ahead — outside 45min default but inside 90min (low → 2x)
        sl.get_wake_time.return_value = time.time() + 70 * 60
        sl.get_wake_confidence.return_value = "low"
        assert blm.should_start(sl) is True

    def test_high_confidence_uses_base_window(self, _isolated_cache_dir):
        """High confidence keeps the tight 45min window."""
        blm = _isolated_cache_dir.BootLoadManager()
        sl = MagicMock()
        sl.get_wake_time.return_value = time.time() + 70 * 60  # 70min, beyond 45
        sl.get_wake_confidence.return_value = "high"
        assert blm.should_start(sl) is False

    def test_missing_confidence_api_defaults_to_high(self, _isolated_cache_dir):
        """Backwards-compatible with learners that lack get_wake_confidence."""
        blm = _isolated_cache_dir.BootLoadManager()
        sl = MagicMock(spec=["get_wake_time"])
        sl.get_wake_time.return_value = time.time() + 10 * 60
        assert blm.should_start(sl) is True


class TestBootLoadCachePersistence:
    def test_cache_roundtrip(self, _isolated_cache_dir):
        BLM = _isolated_cache_dir.BootLoadManager
        Cache = _isolated_cache_dir.BootLoadCache

        blm = BLM()
        blm._cache = Cache(
            briefing_chunks=["a", "b", "c"],
            audio_urls=["u1", "u2"],
            is_complete=True,
            generated_at=time.time(),
        )
        blm._last_run_date = datetime.now().strftime("%Y-%m-%d")
        blm._persist_cache()

        # New instance loads from disk
        blm2 = BLM()
        assert blm2.is_ready
        assert blm2.cache.briefing_chunks == ["a", "b", "c"]
        assert blm2.cache.audio_urls == ["u1", "u2"]

    def test_reset_deletes_cache_file(self, _isolated_cache_dir):
        BLM = _isolated_cache_dir.BootLoadManager
        Cache = _isolated_cache_dir.BootLoadCache

        blm = BLM()
        blm._cache = Cache(briefing_chunks=["x"], is_complete=True, generated_at=1.0)
        blm._last_run_date = datetime.now().strftime("%Y-%m-%d")
        blm._persist_cache()
        assert blm._cache_path().exists()

        blm.reset()
        assert not blm._cache_path().exists()

    def test_stale_cache_files_garbage_collected(self, _isolated_cache_dir):
        BLM = _isolated_cache_dir.BootLoadManager
        cache_dir = BLM()._cache_path().parent

        # Drop a fake cache file from yesterday
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        stale = cache_dir / f"{yesterday}.json"
        stale.write_text(json.dumps({
            "briefing_chunks": ["old"],
            "audio_urls": [],
            "news_chunks": [],
            "generated_at": 1.0,
            "is_complete": True,
        }))
        assert stale.exists()

        # New manager should GC it
        BLM()
        assert not stale.exists()

    def test_incomplete_cache_discarded_on_restore(self, _isolated_cache_dir):
        BLM = _isolated_cache_dir.BootLoadManager
        cache_dir = BLM()._cache_path().parent
        today = datetime.now().strftime("%Y-%m-%d")
        path = cache_dir / f"{today}.json"
        path.write_text(json.dumps({
            "briefing_chunks": ["partial"],
            "audio_urls": [],
            "news_chunks": [],
            "generated_at": 1.0,
            "is_complete": False,  # crashed mid-run
        }))

        blm = BLM()
        assert not blm.is_ready
        assert not path.exists()


class TestBootLoadRunPipeline:
    def test_run_marks_ready_after_briefing_even_if_tts_fails(self, _isolated_cache_dir):
        """Partial cache acceptance: pre-synth failure must not block READY."""
        BLM = _isolated_cache_dir.BootLoadManager
        blm = BLM()

        # Stub world_model + llm_router + session
        wm = MagicMock()
        wm.physical.weather.condition = "晴れ"
        wm.physical.weather.temperature = 18
        wm.biometric_state.sleep.last_update = 0
        wm.digital.gas_state.calendar_events = []
        wm.news_state.daily_chunks = ["world news"]
        wm.news_state.daily_timestamp = time.time()  # fresh — _fetch_news skips refresh

        async def fake_chat(*a, **kw):
            r = MagicMock()
            r.error = None
            r.content = "おはようございます。今日は晴れです。良い一日を。"
            return r

        llm = MagicMock()
        llm.chat = fake_chat

        # Session whose synthesize call always raises (simulate voice-service down)
        class FailingSession:
            async def __aenter__(self_):
                return self_
            async def __aexit__(self_, *a):
                return False

            def post(self_, *a, **kw):
                raise RuntimeError("voice service down")

            def get(self_, *a, **kw):
                raise RuntimeError("news bridge down")

        session = FailingSession()

        async def go():
            blm.start(
                world_model=wm,
                llm_router=llm,
                voice_url="http://voice",
                news_url="http://news",
                backend_url="http://backend",
                session=session,
            )
            # Wait for the background task to finish
            await blm._task

        asyncio.run(go())

        # Briefing succeeded → cache is_complete even though TTS failed
        assert blm.is_ready
        assert blm.cache.briefing_chunks  # has at least one chunk
        assert blm.cache.audio_urls == []  # but no audio

    def test_run_uses_minimal_greeting_when_llm_fails(self, _isolated_cache_dir):
        """LLM failure falls through to the hardcoded greeting fallback,
        and the cache still reaches READY so wake_up gets *something*."""
        BLM = _isolated_cache_dir.BootLoadManager
        blm = BLM()

        wm = MagicMock()
        wm.physical.weather.condition = "unknown"
        wm.biometric_state.sleep.last_update = 0
        wm.digital.gas_state.calendar_events = []
        wm.news_state.daily_chunks = []
        wm.news_state.daily_timestamp = time.time()

        async def empty_chat(*a, **kw):
            r = MagicMock()
            r.error = "llm down"
            r.content = ""
            return r

        llm = MagicMock()
        llm.chat = empty_chat

        class StubSession:
            async def __aenter__(self_):
                return self_
            async def __aexit__(self_, *a):
                return False

            def post(self_, *a, **kw):
                raise RuntimeError("no")
            def get(self_, *a, **kw):
                raise RuntimeError("no")

        async def go():
            blm.start(
                world_model=wm,
                llm_router=llm,
                voice_url="http://v",
                news_url="http://n",
                backend_url="http://b",
                session=StubSession(),
            )
            await blm._task

        asyncio.run(go())
        # Minimal fallback greeting still produces a single chunk → READY
        assert blm.is_ready
        assert blm.cache.briefing_chunks
        assert any("おはよう" in c or "こんにちは" in c for c in blm.cache.briefing_chunks)
