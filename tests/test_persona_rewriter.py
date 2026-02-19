"""Tests for PersonaRewriter — persona-based speak message rewriting."""
import os
from unittest.mock import AsyncMock, patch

import pytest

from character_loader import CharacterConfig, load_character
from llm_client import LLMResponse
from persona_rewriter import PersonaRewriter, _build_persona_prompt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ene_character():
    """Load the ene character template for testing."""
    from pathlib import Path
    config_dir = Path(__file__).resolve().parent.parent / "config"
    with patch.dict(os.environ, {"CHARACTER": "ene"}):
        return load_character(config_dir=config_dir)


@pytest.fixture
def default_character():
    """Default CharacterConfig (dataclass defaults)."""
    return CharacterConfig()


@pytest.fixture
def mock_llm():
    """Mock LLMClient."""
    llm = AsyncMock()
    return llm


@pytest.fixture
def rewriter(ene_character, mock_llm):
    """PersonaRewriter with ene character and mocked LLM."""
    return PersonaRewriter(ene_character, mock_llm)


# ---------------------------------------------------------------------------
# TestBuildPersonaPrompt
# ---------------------------------------------------------------------------

class TestBuildPersonaPrompt:
    def test_default_character_includes_name(self, default_character):
        prompt = _build_persona_prompt(default_character)
        assert "HEMS" in prompt

    def test_ene_identity(self, ene_character):
        prompt = _build_persona_prompt(ene_character)
        assert "エネ" in prompt
        assert "わたし" in prompt
        assert "ご主人" in prompt

    def test_ene_endings_by_tone(self, ene_character):
        prompt = _build_persona_prompt(ene_character)
        assert "語尾(neutral)" in prompt
        assert "語尾(caring)" in prompt
        assert "語尾(alert)" in prompt

    def test_ene_catchphrase(self, ene_character):
        prompt = _build_persona_prompt(ene_character)
        assert "決め台詞" in prompt
        assert "スーパープリティ電脳ガール" in prompt

    def test_ene_vocabulary(self, ene_character):
        prompt = _build_persona_prompt(ene_character)
        assert "好む表現" in prompt
        assert "避ける表現" in prompt
        assert "かしこまりました" in prompt


# ---------------------------------------------------------------------------
# TestRewrite
# ---------------------------------------------------------------------------

class TestRewrite:
    @pytest.mark.asyncio
    async def test_successful_rewrite(self, rewriter, mock_llm):
        mock_llm.chat.return_value = LLMResponse(
            content="ちょっと！GPU90度ですよ！！"
        )
        result = await rewriter.rewrite(
            "GPU温度が90度です。負荷を下げてください。", tone="alert"
        )
        assert result == "ちょっと！GPU90度ですよ！！"
        mock_llm.chat.assert_called_once()
        call_kwargs = mock_llm.chat.call_args
        assert call_kwargs.kwargs["temperature"] == 0.7
        assert call_kwargs.kwargs["max_tokens"] == 80

    @pytest.mark.asyncio
    async def test_llm_error_returns_original(self, rewriter, mock_llm):
        mock_llm.chat.return_value = LLMResponse(error="API timeout")
        result = await rewriter.rewrite("テストメッセージ")
        assert result == "テストメッセージ"

    @pytest.mark.asyncio
    async def test_exception_returns_original(self, rewriter, mock_llm):
        mock_llm.chat.side_effect = RuntimeError("connection lost")
        result = await rewriter.rewrite("テストメッセージ")
        assert result == "テストメッセージ"

    @pytest.mark.asyncio
    async def test_empty_response_returns_original(self, rewriter, mock_llm):
        mock_llm.chat.return_value = LLMResponse(content="")
        result = await rewriter.rewrite("テストメッセージ")
        assert result == "テストメッセージ"

    @pytest.mark.asyncio
    async def test_truncate_over_70_chars(self, rewriter, mock_llm):
        long = "あ" * 100
        mock_llm.chat.return_value = LLMResponse(content=long)
        result = await rewriter.rewrite("テスト")
        assert len(result) == 70

    @pytest.mark.asyncio
    async def test_disabled_skips_rewrite(self, rewriter, mock_llm):
        with patch("persona_rewriter.PERSONA_REWRITE_ENABLED", False):
            result = await rewriter.rewrite("テストメッセージ")
        assert result == "テストメッセージ"
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_tone_in_prompt(self, rewriter, mock_llm):
        mock_llm.chat.return_value = LLMResponse(content="リライト結果")
        await rewriter.rewrite("テスト", tone="alert")
        call_args = mock_llm.chat.call_args[0][0]  # messages list
        user_msg = call_args[1]["content"]
        assert "alert" in user_msg

    @pytest.mark.asyncio
    async def test_quotes_stripped(self, rewriter, mock_llm):
        mock_llm.chat.return_value = LLMResponse(content="「リライト結果」")
        result = await rewriter.rewrite("テスト")
        assert result == "リライト結果"

    @pytest.mark.asyncio
    async def test_double_quotes_stripped(self, rewriter, mock_llm):
        mock_llm.chat.return_value = LLMResponse(content='"Rewritten message"')
        result = await rewriter.rewrite("テスト")
        assert result == "Rewritten message"

    @pytest.mark.asyncio
    async def test_empty_message_returns_empty(self, rewriter, mock_llm):
        result = await rewriter.rewrite("")
        assert result == ""
        mock_llm.chat.assert_not_called()


# ---------------------------------------------------------------------------
# TestUpdateCharacter
# ---------------------------------------------------------------------------

class TestUpdateCharacter:
    def test_update_rebuilds_prompt(self, rewriter, default_character, ene_character):
        old_prompt = rewriter._persona_prompt
        assert "エネ" in old_prompt

        rewriter.update_character(default_character)
        new_prompt = rewriter._persona_prompt
        assert "HEMS" in new_prompt
        assert new_prompt != old_prompt
