"""News urgency scoring via Ollama — ported from voisona-yomiage."""

from loguru import logger
from news_fetcher import Article
from news_summarizer import OllamaClient

URGENCY_SYSTEM = """\
あなたはニュース緊急度判定器です。記事の緊急度を0.0〜1.0で評価してください。\
0.0は日常的なニュース、1.0は即座に知るべき緊急ニュースです。\
数値のみ回答してください。"""


class UrgencyDetector:
    """Ollamaによるニュース緊急度スコアリング."""

    def __init__(self, ollama: OllamaClient, threshold: float = 0.8):
        self.ollama = ollama
        self.threshold = threshold

    async def score(self, article: Article) -> float:
        """記事の緊急度を0.0-1.0でスコアリング."""
        if not await self.ollama.is_available():
            return self._rule_based_score(article)

        prompt = f"タイトル: {article.title}\n要約: {article.summary[:300]}\n\n緊急度スコア:"
        try:
            response = await self.ollama.generate(prompt, system=URGENCY_SYSTEM, temperature=0.1, max_tokens=10)
            score = float(response.strip().split()[0])
            return max(0.0, min(1.0, score))
        except (ValueError, IndexError):
            return self._rule_based_score(article)
        except Exception as e:
            logger.warning(f"Urgency scoring failed: {e}")
            return self._rule_based_score(article)

    def is_urgent(self, score: float) -> bool:
        return score >= self.threshold

    def _rule_based_score(self, article: Article) -> float:
        """ルールベースのフォールバック."""
        title = article.title.lower() + " " + article.summary[:200].lower()
        score = 0.3

        urgent_keywords = [
            "速報",
            "緊急",
            "breaking",
            "地震",
            "津波",
            "台風",
            "テロ",
            "戦争",
            "爆発",
            "大規模",
            "死者",
            "警報",
        ]
        for kw in urgent_keywords:
            if kw in title:
                score += 0.2

        return min(1.0, score)
