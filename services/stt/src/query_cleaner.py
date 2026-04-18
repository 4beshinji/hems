"""
Query cleaner for STT output.
Stage 1: Rule-based filler removal (always active, ~0ms)
Stage 2: LLM rewrite (optional, requires LLM_API_URL)
"""

import os
import re

import aiohttp
from loguru import logger

# --- Stage 1: Rule-based ---

# Japanese fillers (standalone or followed by punctuation)
_FILLERS_JA = re.compile(
    r"(?:^|(?<=\s)|(?<=[、。]))(?:"
    r"えーと|えーっと|えっと|ええと|"
    r"あのー|あのう|あの(?=[、\s])|"
    r"うーん|うーんと|うんと|"
    r"そのー|そのう|"
    r"まあ(?=[、\s])|まぁ(?=[、\s])|"
    r"なんか(?=[、\s])|"
    r"ほら(?=[、\s])|"
    r"こう(?=[、\s])|"
    r"ちょっと(?=[、\s])|"
    r"ですね(?=[、\s])"
    r")(?:[、\s]*)",
    re.UNICODE,
)

# English fillers
_FILLERS_EN = re.compile(
    r"\b(?:um+|uh+|er+|ah+|like|you know|i mean|so|well|basically|actually)\b[,\s]*",
    re.IGNORECASE,
)

# Repeated punctuation / trailing cleanup
_TRAILING_PUNCT = re.compile(r"[、。？！\s]+$")
_MULTI_SPACE = re.compile(r"\s{2,}")
_LEADING_PUNCT = re.compile(r"^[、。\s]+")

# --- Stage 2: LLM rewrite ---

_LLM_SYSTEM_PROMPT = (
    "あなたは音声認識テキストの修正アシスタントです。\n"
    "以下のルールで入力テキストを修正してください：\n"
    "- フィラー除去（えーと、あのー等、残っていれば）\n"
    "- 明らかな誤認識の修正\n"
    "- 省略表現の補完（意図が明確な場合のみ）\n"
    "- 適切な質問/命令形への整形\n"
    "元のテキストの意図は絶対に変えないでください。\n"
    "修正後のテキストのみを出力してください。説明は不要です。"
)


class QueryCleaner:
    def __init__(self) -> None:
        self.llm_rewrite = os.getenv("STT_LLM_REWRITE", "false").lower() == "true"
        self.llm_api_url = os.getenv("LLM_API_URL", "")
        self.llm_model = os.getenv("STT_LLM_MODEL", "") or os.getenv("LLM_MODEL", "")
        self._session: aiohttp.ClientSession | None = None

        if self.llm_rewrite and self.llm_api_url:
            logger.info(f"LLM query rewrite enabled: {self.llm_api_url} model={self.llm_model}")
        elif self.llm_rewrite:
            logger.warning("STT_LLM_REWRITE=true but LLM_API_URL not set, disabled")
            self.llm_rewrite = False

    async def clean(self, text: str, language: str = "ja") -> str:
        """Clean STT output. Returns cleaned text (never empty)."""
        if not text or not text.strip():
            return text

        # Stage 1: rule-based
        cleaned = self._rule_clean(text, language)

        # Stage 2: LLM rewrite (if enabled and text is long enough)
        if self.llm_rewrite and len(cleaned) >= 4:
            try:
                rewritten = await self._llm_rewrite(cleaned)
                if rewritten and len(rewritten) >= 2:
                    cleaned = rewritten
            except Exception as e:
                logger.debug(f"LLM rewrite failed, using rule-based result: {e}")

        return cleaned or text

    def _rule_clean(self, text: str, language: str) -> str:
        """Apply rule-based filler removal."""
        result = text.strip()

        if language.startswith("ja") or _has_japanese(result):
            result = _FILLERS_JA.sub("", result)
        if language.startswith("en") or (language == "auto" and not _has_japanese(result)):
            result = _FILLERS_EN.sub("", result)

        result = _LEADING_PUNCT.sub("", result)
        result = _TRAILING_PUNCT.sub("", result)
        result = _MULTI_SPACE.sub(" ", result)

        return result.strip()

    async def _llm_rewrite(self, text: str) -> str:
        """Rewrite via small LLM."""
        if not self._session:
            self._session = aiohttp.ClientSession()

        url = self.llm_api_url.rstrip("/")
        if not url.endswith("/v1"):
            url += "/v1"

        async with self._session.post(
            f"{url}/chat/completions",
            json={
                "model": self.llm_model,
                "messages": [
                    {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.1,
                "max_tokens": 256,
            },
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                return ""
            data = await resp.json()
            return data["choices"][0]["message"]["content"].strip()

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None


def _has_japanese(text: str) -> bool:
    """Check if text contains Japanese characters."""
    return bool(re.search(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]", text))
