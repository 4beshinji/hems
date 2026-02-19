"""
Persona Rewriter — rewrites rule-engine speak messages in character voice.

Uses a compact LLM call to transform plain Japanese messages into the
configured character's speaking style. Falls back to the original message
on any error.
"""
import os
from loguru import logger


PERSONA_REWRITE_ENABLED = os.getenv("PERSONA_REWRITE_ENABLED", "true").lower() == "true"


class PersonaRewriter:
    def __init__(self, character, llm_client):
        self.character = character
        self.llm_client = llm_client
        self._persona_prompt = _build_persona_prompt(character)

    def update_character(self, character):
        self.character = character
        self._persona_prompt = _build_persona_prompt(character)

    async def rewrite(self, message: str, tone: str = "neutral") -> str:
        if not PERSONA_REWRITE_ENABLED or not message:
            return message

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

            return rewritten

        except Exception as e:
            logger.debug(f"Persona rewrite exception: {e}")
            return message


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
