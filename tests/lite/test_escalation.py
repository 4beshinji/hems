"""
Tests for HEMS Lite Sentinel LLM escalation (unit tests, no API calls).
Run: python -m pytest tests/lite/test_escalation.py -v
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/sentinel/src"))

from escalation import Escalator, EscalationVerdict


class TestResponseParsing:
    def setup_method(self):
        self.escalator = Escalator()

    def test_parse_notify(self):
        content = '{"verdict": "NOTIFY", "level": "HIGH", "reason": "テスト", "message": "通知テスト"}'
        result = self.escalator._parse_response(content)
        assert result.verdict == EscalationVerdict.NOTIFY
        assert result.level == "HIGH"
        assert result.message == "通知テスト"

    def test_parse_watch(self):
        content = '{"verdict": "WATCH", "level": "NORMAL", "reason": "経過観察", "message": ""}'
        result = self.escalator._parse_response(content)
        assert result.verdict == EscalationVerdict.WATCH
        assert result.level == "NORMAL"

    def test_parse_ignore(self):
        content = '{"verdict": "IGNORE", "level": "NORMAL", "reason": "正常", "message": ""}'
        result = self.escalator._parse_response(content)
        assert result.verdict == EscalationVerdict.IGNORE

    def test_parse_markdown_fenced(self):
        content = '```json\n{"verdict": "NOTIFY", "level": "CRITICAL", "reason": "危険", "message": "msg"}\n```'
        result = self.escalator._parse_response(content)
        assert result.verdict == EscalationVerdict.NOTIFY
        assert result.level == "CRITICAL"

    def test_parse_invalid_json(self):
        content = "This is not JSON"
        result = self.escalator._parse_response(content)
        assert result.verdict == EscalationVerdict.WATCH  # safe fallback

    def test_parse_unknown_verdict(self):
        content = '{"verdict": "UNKNOWN", "level": "NORMAL", "reason": "test", "message": ""}'
        result = self.escalator._parse_response(content)
        assert result.verdict == EscalationVerdict.WATCH  # fallback

    def test_parse_unknown_level(self):
        content = '{"verdict": "NOTIFY", "level": "EXTREME", "reason": "test", "message": "msg"}'
        result = self.escalator._parse_response(content)
        assert result.level == "NORMAL"  # fallback


class TestBudget:
    def test_budget_tracking(self):
        escalator = Escalator()
        assert escalator.budget_remaining == 50  # default

        escalator._daily_calls = 48
        from datetime import date
        escalator._daily_date = date.today()
        assert escalator.budget_remaining == 2

    def test_budget_daily_reset(self):
        escalator = Escalator()
        from datetime import date, timedelta
        escalator._daily_date = date.today() - timedelta(days=1)
        escalator._daily_calls = 50
        # Accessing budget_remaining triggers reset
        assert escalator.budget_remaining == 50

    def test_llm_not_available_without_config(self):
        escalator = Escalator()
        # Default: no API key configured
        assert not escalator.llm_available
