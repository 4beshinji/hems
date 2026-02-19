"""
Persona Rewriter — rewrites rule-engine speak messages in character voice.

Uses a compact LLM call to transform plain Japanese messages into the
configured character's speaking style. Falls back to the original message
on any error.

Includes a TTL-based cache to avoid redundant LLM calls for recurring
(message, tone) pairs from rule-engine templates.
"""
import os
import time
from loguru import logger


PERSONA_REWRITE_ENABLED = os.getenv("PERSONA_REWRITE_ENABLED", "true").lower() == "true"
PERSONA_REWRITE_CACHE_TTL = int(os.getenv("PERSONA_REWRITE_CACHE_TTL", "3600"))


class PersonaRewriter:
    def __init__(self, character, llm_client):
        self.character = character
        self.llm_client = llm_client
        self._persona_prompt = _build_persona_prompt(character)
        # Cache: (message, tone) -> (rewritten_text, timestamp)
        self._cache: dict[tuple[str, str], tuple[str, float]] = {}
        self._cache_checks = 0

    def update_character(self, character):
        self.character = character
        self._persona_prompt = _build_persona_prompt(character)
        self._cache.clear()

    async def rewrite(self, message: str, tone: str = "neutral") -> str:
        if not PERSONA_REWRITE_ENABLED or not message:
            return message

        # Check cache
        cache_key = (message, tone)
        now = time.monotonic()
        self._cache_checks += 1

        cached = self._cache.get(cache_key)
        if cached is not None:
            rewritten, ts = cached
            if PERSONA_REWRITE_CACHE_TTL > 0 and (now - ts) < PERSONA_REWRITE_CACHE_TTL:
                return rewritten

        # Periodically prune expired entries
        if self._cache_checks % 100 == 0 or len(self._cache) > 200:
            self._prune_cache(now)

        user_prompt = (
            f"以下のメッセージを、あなたの口調で言い換えてください。\n"
            f"トーン: {tone}\n"
            f"制約: 事実情報（数字・名前・場所）は正確に保持。70字以内。\n"
            f"メッセージ: {message}"
        )

        messages = [
            {"role": "system", "content": self._persona_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self.llm_client.chat(
                messages, temperature=0.7, max_tokens=80,
            )
            if response.error or not response.content:
                logger.debug(f"Persona rewrite failed: {response.error}")
                return message

            rewritten = response.content.strip()
            # Strip surrounding quotes
            if len(rewritten) >= 2 and rewritten[0] in ('"', "'", "「", "『"):
                closing = {'"': '"', "'": "'", "「": "」", "『": "』"}
                expected_close = closing.get(rewritten[0])
                if expected_close and rewritten[-1] == expected_close:
                    rewritten = rewritten[1:-1]

            # Truncate to 70 chars
            if len(rewritten) > 70:
                rewritten = rewritten[:70]

            if not rewritten:
                return message

            # Store in cache
            self._cache[cache_key] = (rewritten, now)

            return rewritten

        except Exception as e:
            logger.debug(f"Persona rewrite exception: {e}")
            return message

    def _prune_cache(self, now: float) -> None:
        """Remove expired entries from the cache."""
        if PERSONA_REWRITE_CACHE_TTL <= 0:
            return
        expired = [
            key for key, (_, ts) in self._cache.items()
            if (now - ts) >= PERSONA_REWRITE_CACHE_TTL
        ]
        for key in expired:
            del self._cache[key]


def _build_persona_prompt(character) -> str:
    """Build a compact system prompt from CharacterConfig for rewriting."""
    identity = character.identity
    personality = character.personality
    style = character.speaking_style

    lines = [
        f"あなたは「{identity.name}」です。",
        f"一人称: {identity.first_person}、二人称: {identity.second_person}",
        f"性格: {personality.archetype}",
    ]

    # Top 4 traits
    if personality.traits:
        traits = personality.traits[:4]
        lines.append(f"特徴: {', '.join(traits)}")

    # First 2 lines of behavioral_notes
    if personality.behavioral_notes:
        notes = personality.behavioral_notes.strip().split("\n")[:2]
        for note in notes:
            note = note.strip().lstrip("- ")
            if note:
                lines.append(f"行動: {note}")

    # Endings by tone (up to 3 each)
    endings = style.endings
    for tone_name in ("neutral", "caring", "alert"):
        tone_endings = getattr(endings, tone_name, [])
        if tone_endings:
            lines.append(f"語尾({tone_name}): {', '.join(tone_endings[:3])}")

    # Vocabulary
    vocab = style.vocabulary
    if vocab.prefer:
        lines.append(f"好む表現: {', '.join(vocab.prefer[:5])}")
    if vocab.avoid:
        lines.append(f"避ける表現: {', '.join(vocab.avoid[:4])}")
    if vocab.catchphrase:
        lines.append(f"決め台詞: {vocab.catchphrase}")

    lines.append("メッセージをこのキャラクターの口調でリライトしてください。リライト結果のみ出力。")

    return "\n".join(lines)
