"""
Regression tests for AutomationEngine._llm_review.

chat() returns an LLMResponse object, not a str. A prior bug treated the
response as a string ((response or "").strip() / .splitlines()), which raised
AttributeError and forced every llm_review-mode rule to silently skip. These
tests confirm a "fire" verdict is honoured and a real LLM error skips cleanly.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from automation_engine import AutomationEngine
from llm_client import LLMResponse


def _make_engine(llm_response):
    llm_client = MagicMock()
    llm_client.chat = AsyncMock(return_value=llm_response)
    world_model = MagicMock()
    world_model.get_llm_context = MagicMock(return_value="state")
    return AutomationEngine(
        dispatcher=MagicMock(),
        scene_executor=MagicMock(),
        dashboard_client=MagicMock(),
        llm_client=llm_client,
        world_model=world_model,
        sanitizer=MagicMock(),
    )


@pytest.mark.asyncio
async def test_llm_review_fire_verdict_honoured():
    engine = _make_engine(LLMResponse(content="fire\n発火が適切です"))
    should_fire, reason = await engine._llm_review({"name": "rule"})
    assert should_fire is True
    assert "発火" in reason


@pytest.mark.asyncio
async def test_llm_review_skip_verdict_honoured():
    engine = _make_engine(LLMResponse(content="skip\n雨予報のため"))
    should_fire, reason = await engine._llm_review({"name": "rule"})
    assert should_fire is False
    assert "雨" in reason


@pytest.mark.asyncio
async def test_llm_review_error_response_skips_without_raising():
    engine = _make_engine(LLMResponse(error="HTTP 500"))
    should_fire, reason = await engine._llm_review({"name": "rule"})
    assert should_fire is False
    assert "HTTP 500" in reason
