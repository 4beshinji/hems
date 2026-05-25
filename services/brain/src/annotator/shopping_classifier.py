"""Shopping item classifier — seed rules → HTTP cache → LLM fallback.

Priority (highest wins):
  user_override > promoted > seed > llm > default (None)

Sync path (``classify``) covers seed + in-memory cache only.
Async path (``classify_async``) adds the HTTP cache + LLM fallback.
The MQTT handler uses the async path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from brain_constants import backend_auth_headers

from .cache import ClassifierCache
from .rules import match_rule

if TYPE_CHECKING:
    import aiohttp

    from llm_router import LLMRouter


# Canonical categories — mirrored on backend FrequentPlace.category values.
ALLOWED_CATEGORIES = {"drugstore", "supermarket", "convenience", "home_center", "other"}

LLM_PROMPT = (
    "あなたは買い物アイテムのカテゴリ分類器です。以下のアイテムを、最も適した店舗カテゴリ"
    "に分類してください。\n\n"
    "選択肢:\n"
    "  drugstore    — 薬局・ドラッグストア (医薬品・化粧品・衛生用品など)\n"
    "  supermarket  — スーパーマーケット (食料品全般・日用品)\n"
    "  convenience  — コンビニ (軽食・切手・コピー用紙など少量品)\n"
    "  home_center  — ホームセンター (工具・園芸・DIY・電気小物)\n"
    "  other        — 上記に当てはまらない\n\n"
    "アイテム: {name}\n\n"
    "回答は英小文字のカテゴリ名1つだけ出力してください。説明不要。"
)


class ShoppingClassifier:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        backend_url: str,
        *,
        cache: ClassifierCache | None = None,
        llm_router: LLMRouter | None = None,
    ) -> None:
        self.session = session
        self.backend_url = backend_url.rstrip("/")
        self.cache = cache or ClassifierCache(
            session=session,
            backend_url=backend_url,
        )
        self.llm_router = llm_router

    # ---- sync path (seed + L1 memory) ------------------------------------ #

    def classify(self, name: str) -> str | None:
        if not name:
            return None
        mem = self.cache.get_memory("shopping", name)
        if mem is not None:
            return mem.value
        category = match_rule(name)
        if category:
            self.cache.put_memory("shopping", name, category, "seed")
            return category
        return None

    # ---- async path (seed → HTTP cache → LLM fallback) ------------------- #

    async def classify_async(self, name: str) -> str | None:
        sync_hit = self.classify(name)
        if sync_hit:
            return sync_hit

        entry = await self.cache.get("shopping", name)
        if entry is not None and entry.value in ALLOWED_CATEGORIES:
            return entry.value

        if self.llm_router is None:
            return None

        category = await self._llm_classify(name)
        if category:
            await self.cache.put("shopping", name, category, "llm")
        return category

    async def _llm_classify(self, name: str) -> str | None:
        try:
            resp = await self.llm_router.chat(
                [
                    {
                        "role": "system",
                        "content": "You classify shopping items. Output only a single lowercase category word.",
                    },
                    {"role": "user", "content": LLM_PROMPT.format(name=name)},
                ],
                task_type="shopping_classify",
                temperature=0.0,
                max_tokens=16,
            )
        except Exception as exc:
            logger.warning("shopping LLM classify error for {!r}: {}", name, exc)
            return None

        text = (getattr(resp, "content", None) or "").strip().lower()
        # Some models prepend explanation or quote the answer — take the last word.
        token = text.split()[-1].strip(".,`'\"") if text else ""
        if token in ALLOWED_CATEGORIES:
            return token
        logger.debug("shopping LLM returned unrecognized token: {!r}", text)
        return None

    # ---- MQTT handler (called from main.Brain._process_mqtt) ------------- #

    async def handle_added_event(self, payload: dict) -> bool:
        item_id = payload.get("id")
        name = payload.get("name") or ""
        if not item_id or not name:
            return False
        category = await self.classify_async(name)
        if category is None:
            logger.debug("Shopping classifier: no match for {!r}", name)
            return False
        return await self._patch_store_category(int(item_id), category)

    async def _patch_store_category(self, item_id: int, store_category: str) -> bool:
        url = f"{self.backend_url}/shopping/{item_id}"
        try:
            async with self.session.patch(
                url,
                headers=backend_auth_headers(),
                json={"store_category": store_category},
                timeout=10,
            ) as resp:
                if resp.status == 200:
                    logger.info(
                        "Shopping classified: id={} → store_category={}",
                        item_id,
                        store_category,
                    )
                    return True
                text = await resp.text()
                logger.warning(
                    "Shopping PATCH failed: id={} status={} body={}",
                    item_id,
                    resp.status,
                    text[:200],
                )
        except Exception as exc:
            logger.error("Shopping PATCH error: id={} err={}", item_id, exc)
        return False

    # ---- Purchase cycle learning ---------------------------------------- #

    async def handle_purchased_event(self, payload: dict) -> bool:
        """Learn purchase cycles from /purchased events.

        Gates on at least 3 historical purchases of the same item before flagging
        as recurring (avoid one-off purchases being misclassified as periodic).
        Inferred cycle median (in days) is patched back to backend.
        """
        item_name = payload.get("name") or ""
        if not item_name:
            return False

        try:
            url = f"{self.backend_url}/shopping/purchase-history"
            params = {"name": item_name, "limit": 10}
            async with self.session.get(url, headers=backend_auth_headers(), params=params, timeout=10) as resp:
                if resp.status != 200:
                    return False
                history = await resp.json()
        except Exception as exc:
            logger.warning("purchase-history fetch error for {!r}: {}", item_name, exc)
            return False

        # Need ≥3 purchases (current + 2 prior) to detect a cycle
        purchases = history if isinstance(history, list) else history.get("items", [])
        if len(purchases) < 3:
            logger.debug(
                "Shopping purchase: only {} entries for {!r} — need ≥3 to learn cycle",
                len(purchases),
                item_name,
            )
            return False

        # Median day-gap between consecutive purchases
        from datetime import datetime as _dt

        timestamps: list[float] = []
        for p in purchases:
            ts_str = p.get("purchased_at") or p.get("created_at")
            if not ts_str:
                continue
            try:
                timestamps.append(_dt.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp())
            except (ValueError, AttributeError):
                continue
        if len(timestamps) < 3:
            return False
        timestamps.sort()
        gaps_days = [(timestamps[i + 1] - timestamps[i]) / 86400 for i in range(len(timestamps) - 1)]
        gaps_days.sort()
        median_days = gaps_days[len(gaps_days) // 2]
        if median_days < 1:
            return False

        # Patch shopping item with inferred recurrence (only if currently 0)
        item_id = payload.get("id")
        if not item_id:
            return False

        recurrence_days = round(median_days)
        try:
            patch_url = f"{self.backend_url}/shopping/{int(item_id)}"
            async with self.session.patch(
                patch_url,
                headers=backend_auth_headers(),
                json={"is_recurring": True, "recurrence_days": recurrence_days},
                timeout=10,
            ) as resp:
                if resp.status == 200:
                    logger.info(
                        "Shopping cycle learned: {!r} → every ~{} days (n={})",
                        item_name,
                        recurrence_days,
                        len(purchases),
                    )
                    return True
        except Exception as exc:
            logger.warning("Shopping recurrence PATCH error: {}", exc)
        return False
