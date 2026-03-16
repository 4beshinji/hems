"""News summarizer via Ollama — ported from voisona-yomiage."""

import re

import aiohttp
from loguru import logger

from news_fetcher import Article

SUMMARY_SYSTEM = """\
あなたはニュースアナウンサーです。主要ニュースを簡潔に日本語で読み上げてください。
各記事は1-2文で要約し、自然な話し言葉で繋げてください。
マークダウン記法（**や##等）は使わないでください。
アルファベットは使わず日本語のカタカナ表記にしてください\
（例: JR→ジェイアール、BBC→ビービーシー、AI→エーアイ）。
ニュースをカテゴリごとにまとめ、各カテゴリの冒頭に【カテゴリ名】を付けてください。
カテゴリ例: 【国内】【国際】【経済】【スポーツ】【社会】【科学・技術】など。"""

SUMMARY_PROMPT = """\
以下の記事を日本語で簡潔にまとめてください。
音声読み上げ用のプレーンテキストにしてください（マークダウン不可）。

{articles}

重要度の高い順に5-10件を選び、カテゴリごとにまとめてください。
形式:
【国内】
1. ニュース内容。
2. ニュース内容。
【国際】
3. ニュース内容。
..."""

CATEGORY_PATTERN = re.compile(r"【[^】]+】")

TRANSLATE_SYSTEM = "あなたは翻訳者です。以下のテキストを自然な日本語に翻訳してください。"

MAX_CHUNK_CHARS = 300


def split_by_category(text: str) -> list[str]:
    """【カテゴリ名】区切りでテキストを分割.

    カテゴリが見つからない場合やカテゴリ内が長すぎる場合は
    文単位でさらに分割する。
    """
    parts = CATEGORY_PATTERN.split(text)
    headers = CATEGORY_PATTERN.findall(text)

    raw_chunks: list[str] = []
    if parts and parts[0].strip():
        raw_chunks.append(parts[0].strip())
    for header, body in zip(headers, parts[1:]):
        body = body.strip()
        if body:
            raw_chunks.append(f"{header}\n{body}")

    if not raw_chunks:
        raw_chunks = [text]

    result: list[str] = []
    for chunk in raw_chunks:
        if len(chunk) <= MAX_CHUNK_CHARS:
            result.append(chunk)
        else:
            result.extend(_split_long_chunk(chunk))
    return result


def _split_long_chunk(text: str) -> list[str]:
    """長いチャンクを文末（。）で分割."""
    sentences = re.split(r"(?<=。)", text)
    chunks: list[str] = []
    buf = ""
    for s in sentences:
        if not s:
            continue
        if len(buf) + len(s) <= MAX_CHUNK_CHARS:
            buf += s
        else:
            if buf:
                chunks.append(buf)
            buf = s
    if buf:
        chunks.append(buf)
    return chunks


class OllamaClient:
    """Simplified Ollama REST API client (generate + is_available)."""

    def __init__(self, url: str = "http://localhost:11434", model: str = "qwen3.5"):
        self.url = url.rstrip("/")
        self.model = model

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120)
        ) as session:
            async with session.post(f"{self.url}/api/chat", json=body) as resp:
                if resp.status != 200:
                    detail = await resp.text()
                    raise RuntimeError(f"Ollama chat failed: {resp.status} {detail}")
                result = await resp.json()
                return result.get("message", {}).get("content", "")

    async def is_available(self) -> bool:
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                async with session.get(f"{self.url}/api/tags") as resp:
                    return resp.status == 200
        except Exception:
            return False


class NewsSummarizer:
    """Ollamaによるニュースサマリ生成."""

    def __init__(self, ollama: OllamaClient):
        self.ollama = ollama

    async def daily_summary(self, articles: list[Article]) -> str:
        """主要ニュースの日次サマリを生成."""
        if not articles:
            return "本日のニュースはありません。"

        if not await self.ollama.is_available():
            logger.warning("Ollama unavailable, using raw titles")
            return self._fallback_summary(articles)

        articles_text = "\n".join(
            f"- [{a.source}] {a.title}: {a.summary[:200]}" for a in articles[:15]
        )
        prompt = SUMMARY_PROMPT.format(articles=articles_text)

        try:
            return await self.ollama.generate(prompt, system=SUMMARY_SYSTEM)
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return self._fallback_summary(articles)

    async def translate_if_needed(self, article: Article, target_lang: str = "ja") -> str:
        """海外記事を必要に応じて翻訳."""
        if article.language == target_lang:
            return f"{article.title}。{article.summary}"

        if not await self.ollama.is_available():
            return f"{article.title}. {article.summary}"

        text = f"{article.title}\n{article.summary}"
        try:
            return await self.ollama.generate(text, system=TRANSLATE_SYSTEM)
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return text

    def _fallback_summary(self, articles: list[Article]) -> str:
        lines = ["本日の主なニュースです。"]
        for a in articles[:10]:
            lines.append(f"{a.title}。")
        return "\n".join(lines)
