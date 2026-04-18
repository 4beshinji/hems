"""Adjust cached event_lead entries based on observed trigger-drift.

We treat ``trigger_drift_sec`` from play-log as the offset between when we
*scheduled* the reminder and when the phone *actually* played it. Positive
drift = the phone played late (user silent, delayed ack); negative drift
= early. If a given event consistently drifts in one direction we shift
``lead_time_min`` on the cached EventPlan so the next run is closer to the
user's real preference.

Scope — this only touches ``kind="event_lead"`` entries; shopping cache
entries have no temporal component.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    import aiohttp


# Bounds on the computed shift so a single outlier play can't swing the lead.
MAX_SHIFT_MIN = 10
MIN_SAMPLES = 3
LEAD_FLOOR = 5
LEAD_CEILING = 120


class AckLearner:
    def __init__(
        self,
        *,
        session: aiohttp.ClientSession,
        backend_url: str,
    ):
        self.session = session
        self.backend_url = backend_url.rstrip("/")

    async def run(self, *, since_days: int = 30) -> int:
        """Consume recent play-log and update cached event_lead entries.

        Returns the number of cache rows that were actually adjusted.
        """
        logs = await self._fetch_play_logs(since_days=since_days)
        if not logs:
            return 0

        # Group drifts by clip_id — clip ids are deterministic per event
        # title+HHMM so they collapse the same recurring event across days.
        drifts: dict[str, list[int]] = defaultdict(list)
        for row in logs:
            if not row.get("clip_id", "").startswith("event_"):
                continue
            drift = row.get("trigger_drift_sec")
            if drift is not None:
                drifts[row["clip_id"]].append(int(drift))

        # Pre-fetch all event_lead cache entries once for prefix matching.
        all_event_leads = await self._list_event_lead_entries()
        prefix_map: dict[str, dict] = {}
        for entry in all_event_leads:
            prefix_map[entry["key_hash"][:12]] = entry

        updates = 0
        for clip_id, vals in drifts.items():
            if len(vals) < MIN_SAMPLES:
                continue
            shift = self._shift_from_drift(vals)
            if shift == 0:
                continue
            title_hash = _title_hash_from_clip_id(clip_id)
            if not title_hash:
                continue
            entry = prefix_map.get(title_hash)
            if entry is None:
                continue
            if await self._adjust_cached_plan_entry(entry, shift):
                updates += 1

        logger.info("[ack_learner] updated {} event_lead entr(y|ies)", updates)
        return updates

    def _shift_from_drift(self, drifts: list[int]) -> int:
        """Convert a list of drift-seconds into a (bounded) minute shift.

        Positive drift → phone late → schedule earlier (shift lead UP).
        Negative drift → phone early → schedule later (shift lead DOWN).
        """
        median_sec = int(statistics.median(drifts))
        if abs(median_sec) < 60:  # smaller than a full minute — ignore noise
            return 0
        minutes = round(median_sec / 60)
        return max(-MAX_SHIFT_MIN, min(MAX_SHIFT_MIN, minutes))

    async def _fetch_play_logs(self, *, since_days: int) -> list[dict]:
        url = f"{self.backend_url}/mobile/voice-capsule/play-log?since_days={since_days}"
        try:
            async with self.session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning("[ack_learner] play-log fetch HTTP {}", resp.status)
        except Exception as exc:
            logger.warning("[ack_learner] play-log fetch error: {}", exc)
        return []

    async def _adjust_cached_plan_entry(self, entry: dict, shift_min: int) -> bool:
        """Shift ``lead_time_min`` on an existing event_lead cache row."""
        try:
            plan = json.loads(entry["value_json"])
        except Exception:
            return False

        old = int(plan.get("lead_time_min", 30))
        new = max(LEAD_FLOOR, min(LEAD_CEILING, old + shift_min))
        if new == old:
            return False

        plan["lead_time_min"] = new
        return await self._put_cache_entry(
            kind="event_lead",
            key_hash=entry["key_hash"],
            value=json.dumps(plan, ensure_ascii=False),
            source=entry.get("source", "llm"),
        )

    async def _list_event_lead_entries(self) -> list[dict]:
        url = f"{self.backend_url}/classifier-cache?kind=event_lead"
        try:
            async with self.session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as exc:
            logger.debug("[ack_learner] cache list error: {}", exc)
        return []

    async def _put_cache_entry(
        self,
        *,
        kind: str,
        key_hash: str,
        value: str,
        source: str,
    ) -> bool:
        url = f"{self.backend_url}/classifier-cache"
        payload = {
            "kind": kind,
            "key_hash": key_hash,
            "value_json": value,
            "source": source,
        }
        try:
            async with self.session.post(url, json=payload, timeout=10) as resp:
                return resp.status == 201
        except Exception as exc:
            logger.warning("[ack_learner] cache put error: {}", exc)
            return False


def _title_hash_from_clip_id(clip_id: str) -> str | None:
    """Extract the 12-hex-char title hash from ``event_<hash>_HHMM``."""
    if not clip_id.startswith("event_"):
        return None
    body = clip_id[len("event_") :]
    parts = body.rsplit("_", 1)
    if len(parts) != 2 or not parts[1].isdigit() or len(parts[1]) != 4:
        return None
    h = parts[0]
    if len(h) == 12 and all(c in "0123456789abcdef" for c in h):
        return h
    return None
