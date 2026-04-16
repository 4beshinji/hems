"""Turn a ClipSpec's seed into final transcript text.

Defers all persona expression to PersonaRewriter so the capsule pipeline
stays aligned with the 2-stage character separation (stage 1 = raw
thinking, stage 2 = persona overlay).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from persona_rewriter import PersonaRewriter


class TranscriptWriter:
    def __init__(self, persona_rewriter: "PersonaRewriter | None" = None):
        self.persona_rewriter = persona_rewriter

    async def write(self, seed: str, *, tone: str) -> str:
        if not self.persona_rewriter:
            return seed
        try:
            return await self.persona_rewriter.rewrite(seed, tone=tone)
        except Exception as exc:  # noqa: BLE001 — persona is best-effort
            logger.warning("PersonaRewriter failed for clip — falling back to seed: {}", exc)
            return seed
