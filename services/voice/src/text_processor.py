"""Text preprocessing for TTS — cleanup, normalization, markdown strip.

Ported from voisona-yomiage nlp/text_processor.py.
"""

import re
import unicodedata


class TextProcessor:
    """テキスト前処理."""

    def process(self, text: str) -> str:
        """テキストをTTS用にクリーニング."""
        text = self._normalize(text)
        text = self._normalize_punctuation(text)
        text = self._clean_whitespace(text)
        return text

    def _normalize(self, text: str) -> str:
        return unicodedata.normalize("NFKC", text)

    def _normalize_punctuation(self, text: str) -> str:
        # マークダウン記号除去
        text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
        # 三点リーダー統一
        text = re.sub(r"\.{3,}", "…", text)
        text = re.sub(r"。{2,}", "。", text)
        # ダッシュ統一
        text = re.sub(r"[―—–]{2,}", "――", text)
        return text

    @staticmethod
    def has_alphabet(text: str) -> bool:
        """テキストにアルファベットが含まれるか."""
        return bool(re.search(r"[A-Za-z]", text))

    def _clean_whitespace(self, text: str) -> str:
        # 行頭の全角スペース（字下げ）を除去
        text = re.sub(r"^[　 ]+", "", text, flags=re.MULTILINE)
        # 連続空行を1つに
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
