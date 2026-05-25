"""Tests for LLM cost/token metering (Group E, ported from SOMS).

Covers: (a) LLMResponse.usage normalization across providers, and (b) the
event-store round-trip that persists the new nullable token/GPU columns.
"""

import json

import pytest

from llm_client import LLMClient, LLMResponse


class _FakeResp:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)


class _FakeSession:
    """Minimal aiohttp-session stand-in: every post() returns the same payload."""

    def __init__(self, payload):
        self._payload = payload

    def post(self, *a, **k):
        return _FakeResp(200, self._payload)


class TestLLMResponseUsage:
    def test_usage_defaults_none(self):
        assert LLMResponse().usage is None

    @pytest.mark.asyncio
    async def test_openai_usage_captured(self):
        payload = {
            "choices": [{"message": {"content": "hi", "tool_calls": []}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        c = LLMClient(api_url="http://x/v1", session=_FakeSession(payload), model="m", provider="openai")
        r = await c.chat([{"role": "user", "content": "x"}])
        assert r.usage == {"prompt_tokens": 10, "completion_tokens": 5}

    @pytest.mark.asyncio
    async def test_ollama_usage_normalized(self):
        payload = {"message": {"content": "hi"}, "prompt_eval_count": 12, "eval_count": 7}
        c = LLMClient(api_url="http://x/v1", session=_FakeSession(payload), model="m", provider="ollama")
        r = await c.chat([{"role": "user", "content": "x"}])
        assert r.usage == {"prompt_tokens": 12, "completion_tokens": 7}

    @pytest.mark.asyncio
    async def test_anthropic_usage_normalized(self):
        payload = {
            "content": [{"type": "text", "text": "hi"}],
            "usage": {"input_tokens": 20, "output_tokens": 8},
        }
        c = LLMClient(session=_FakeSession(payload), model="m", provider="anthropic")
        r = await c.chat([{"role": "user", "content": "x"}])
        assert r.usage == {"prompt_tokens": 20, "completion_tokens": 8}

    @pytest.mark.asyncio
    async def test_no_usage_is_none(self):
        payload = {"choices": [{"message": {"content": "hi", "tool_calls": []}}]}
        c = LLMClient(api_url="http://x/v1", session=_FakeSession(payload), model="m", provider="openai")
        r = await c.chat([{"role": "user", "content": "x"}])
        assert r.usage is None


class TestDecisionTokenPersistence:
    @pytest.mark.asyncio
    async def test_tokens_persisted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'ev.db'}")
        from event_store import EventWriter, init_db

        engine = await init_db()
        assert engine is not None
        w = EventWriter(engine)
        w.record_decision(
            cycle_duration=1.0,
            iterations=2,
            total_tool_calls=3,
            prompt_tokens=100,
            completion_tokens=40,
            gpu_util_pct=55.5,
        )
        await w._flush()

        from sqlalchemy import text

        async with engine.begin() as conn:
            row = (
                await conn.execute(
                    text("SELECT prompt_tokens, completion_tokens, gpu_util_pct, gpu_power_w FROM llm_decisions")
                )
            ).fetchone()
        assert row == (100, 40, 55.5, None)
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_rule_based_cycle_leaves_tokens_null(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'ev2.db'}")
        from event_store import EventWriter, init_db

        engine = await init_db()
        w = EventWriter(engine)
        w.record_decision(cycle_duration=0.5, iterations=1, total_tool_calls=1)
        await w._flush()

        from sqlalchemy import text

        async with engine.begin() as conn:
            row = (await conn.execute(text("SELECT prompt_tokens, completion_tokens FROM llm_decisions"))).fetchone()
        assert row == (None, None)
        await engine.dispose()
