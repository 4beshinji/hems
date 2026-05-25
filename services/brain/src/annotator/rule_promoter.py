"""Promote hot ClassifierCache rows: ``source=llm`` → ``source=promoted``.

Runs on a schedule (or on-demand). For every cached classification whose
``hit_count >= PROMOTION_THRESHOLD`` and whose current source is still
``llm``, the promoter:

1. POSTs the same entry back with ``source="promoted"`` — backend upserts
   in-place so ``hit_count`` is preserved.
2. Appends a line to the Obsidian vault at
   ``HEMS/learnings/classifier_rules.md`` so the user can audit learned
   rules and hand-tune them.

Kept intentionally small — the promotion decision has to live somewhere
and doing it from Python with a regex seed file is clearer than baking it
into the LLM path.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from brain_constants import backend_auth_headers

if TYPE_CHECKING:
    import aiohttp


PROMOTION_THRESHOLD = 3
LEARNINGS_NOTE_PATH = "HEMS/learnings/classifier_rules.md"


class RulePromoter:
    def __init__(
        self,
        *,
        session: aiohttp.ClientSession,
        backend_url: str,
        obsidian_url: str = "",
    ):
        self.session = session
        self.backend_url = backend_url.rstrip("/")
        self.obsidian_url = obsidian_url.rstrip("/")

    async def run(self) -> int:
        """Promote all eligible entries. Returns the number promoted."""
        candidates = await self._fetch_candidates()
        if not candidates:
            return 0

        promoted: list[dict] = []
        for entry in candidates:
            if await self._promote(entry):
                promoted.append(entry)

        if promoted and self.obsidian_url:
            await self._write_learnings(promoted)

        logger.info("[rule_promoter] promoted {} entries", len(promoted))
        return len(promoted)

    async def _fetch_candidates(self) -> list[dict]:
        params = f"?source=llm&min_hit_count={PROMOTION_THRESHOLD}"
        url = f"{self.backend_url}/classifier-cache{params}"
        try:
            async with self.session.get(url, headers=backend_auth_headers(), timeout=15) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning("[rule_promoter] fetch failed: HTTP {}", resp.status)
        except Exception as exc:
            logger.warning("[rule_promoter] fetch error: {}", exc)
        return []

    async def _promote(self, entry: dict) -> bool:
        url = f"{self.backend_url}/classifier-cache"
        payload = {
            "kind": entry["kind"],
            "key_hash": entry["key_hash"],
            "value_json": entry["value_json"],
            "source": "promoted",
        }
        try:
            async with self.session.post(
                url,
                headers=backend_auth_headers(),
                json=payload,
                timeout=10,
            ) as resp:
                if resp.status == 201:
                    return True
                logger.warning(
                    "[rule_promoter] promote failed for {}/{}... status={}",
                    entry["kind"],
                    entry["key_hash"][:8],
                    resp.status,
                )
        except Exception as exc:
            logger.warning("[rule_promoter] promote error: {}", exc)
        return False

    async def _write_learnings(self, promoted: list[dict]) -> None:
        """Append the newly-promoted entries to the Obsidian learnings note."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"## {ts} — promoted {len(promoted)} rule(s)\n"]
        for e in promoted:
            lines.append(
                f"- `{e['kind']}` / `{e['key_hash'][:10]}…` "
                f"→ value={e.get('value_json', '').strip()[:80]} "
                f"(hit_count={e.get('hit_count', '?')})"
            )
        body = "\n".join(lines) + "\n"

        url = f"{self.obsidian_url}/api/notes/write"
        try:
            async with self.session.post(
                url,
                json={
                    "title": LEARNINGS_NOTE_PATH,
                    "content": body,
                    "category": "learnings",
                },
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    logger.warning("[rule_promoter] obsidian write HTTP {}", resp.status)
        except Exception as exc:
            logger.warning("[rule_promoter] obsidian write error: {}", exc)
