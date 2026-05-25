import json
import time
from datetime import datetime as _dt
from typing import Any

import aiohttp


class ExternalToolHandlers:
    async def _handle_search_notes(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.obsidian_url:
            return {"success": False, "error": "Obsidian bridge not configured"}
        try:
            async with self._session.post(
                f"{self.obsidian_url}/api/notes/search",
                json={
                    "query": args.get("query", ""),
                    "tags": args.get("tags"),
                    "path_prefix": args.get("path_prefix"),
                    "max_results": args.get("max_results", 5),
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_write_note(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.obsidian_url:
            return {"success": False, "error": "Obsidian bridge not configured"}
        try:
            async with self._session.post(
                f"{self.obsidian_url}/api/notes/write",
                json={
                    "title": args.get("title", ""),
                    "content": args.get("content", ""),
                    "tags": args.get("tags"),
                    "category": args.get("category"),
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_recent_notes(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.obsidian_url:
            return {"success": False, "error": "Obsidian bridge not configured"}
        try:
            async with self._session.get(
                f"{self.obsidian_url}/api/notes/recent",
                params={"limit": args.get("limit", 5)},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_list_note_tags(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.obsidian_url:
            return {"success": False, "error": "Obsidian bridge not configured"}
        try:
            async with self._session.get(
                f"{self.obsidian_url}/api/notes/tags",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_news_summary(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get latest news summary from world model cache or news-bridge API."""
        ns = self.world_model.news_state
        if ns.daily_timestamp > 0:
            age_min = int((time.time() - ns.daily_timestamp) / 60)
            result = {
                "summary": ns.daily_summary,
                "chunks": ns.daily_chunks,
                "article_count": len(ns.daily_chunks),
                "age_minutes": age_min,
            }
            if ns.urgent_articles:
                recent = [a for a in ns.urgent_articles if time.time() - a.get("timestamp", 0) < 3600]
                if recent:
                    result["urgent"] = recent
            return {"success": True, "result": json.dumps(result, ensure_ascii=False)}

        if self.news_url and self._session:
            try:
                async with self._session.get(
                    f"{self.news_url}/api/news/latest",
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                    return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": True, "result": "ニュースデータがまだありません"}

    async def _handle_get_recent_emails(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get recent Gmail threads from world_model.gas_state.gmail_recent."""
        gs = self.world_model.gas_state
        threads = gs.gmail_recent or []
        if not threads:
            return {"success": True, "result": "Gmailスレッド情報がありません"}

        limit = max(1, min(int(args.get("limit", 10)), 50))
        sender_q = (args.get("sender_contains") or "").lower()
        subject_q = (args.get("subject_contains") or "").lower()
        unread_only = bool(args.get("unread_only", False))

        results = []
        for t in threads:
            if not isinstance(t, dict):
                continue
            sender = str(t.get("from") or t.get("sender") or "")
            subject = str(t.get("subject") or "")
            snippet = str(t.get("snippet") or "")
            unread = bool(t.get("unread", False))
            if unread_only and not unread:
                continue
            if sender_q and sender_q not in sender.lower():
                continue
            if subject_q and subject_q not in subject.lower():
                continue
            results.append(
                {
                    "from": sender[:80],
                    "subject": subject[:100],
                    "snippet": snippet[:50],
                    "unread": unread,
                    "thread_id": t.get("thread_id") or t.get("id"),
                }
            )
            if len(results) >= limit:
                break

        return {
            "success": True,
            "result": json.dumps({"threads": results, "total": len(results)}, ensure_ascii=False),
        }

    async def _handle_gas_query_free_slots(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return calendar free slots with HH:MM-HH:MM ranges from gas_state.free_slots."""
        gs = self.world_model.gas_state
        if not gs.free_slots:
            return {"success": True, "result": "空きスロット情報がありません"}

        date_range_hours = max(1, min(int(args.get("date_range_hours", 24)), 168))
        min_minutes = max(15, min(int(args.get("min_duration_minutes", 60)), 480))
        limit = max(1, min(int(args.get("limit", 5)), 20))

        cutoff_ts = time.time() + date_range_hours * 3600
        results = []
        for slot in gs.free_slots:
            if slot.duration_minutes < min_minutes:
                continue
            try:
                start_dt = _dt.fromisoformat(slot.start.replace("Z", "+00:00"))
                end_dt = _dt.fromisoformat(slot.end.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            if start_dt.timestamp() > cutoff_ts:
                continue
            results.append(
                {
                    "start": start_dt.strftime("%Y-%m-%d %H:%M"),
                    "end": end_dt.strftime("%Y-%m-%d %H:%M"),
                    "range": f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}",
                    "duration_minutes": slot.duration_minutes,
                }
            )
            if len(results) >= limit:
                break

        return {
            "success": True,
            "result": json.dumps({"slots": results, "total": len(results)}, ensure_ascii=False),
        }

    async def _handle_gas_query_sheet(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return cached sheet data from gas_state.sheets[name]."""
        gs = self.world_model.gas_state
        name = (args.get("name") or "").strip()
        if not name:
            return {"success": False, "error": "name is required"}

        sheet = gs.sheets.get(name)
        if not sheet:
            available = list(gs.sheets.keys())
            return {
                "success": True,
                "result": json.dumps(
                    {
                        "found": False,
                        "name": name,
                        "available_sheets": available[:20],
                    },
                    ensure_ascii=False,
                ),
            }

        max_rows = max(1, min(int(args.get("max_rows", 50)), 200))
        rows = sheet.values[:max_rows] if isinstance(sheet.values, list) else []
        return {
            "success": True,
            "result": json.dumps(
                {
                    "found": True,
                    "name": name,
                    "headers": sheet.headers,
                    "rows": rows,
                    "row_count": len(rows),
                    "total_rows": len(sheet.values) if isinstance(sheet.values, list) else 0,
                    "last_update": sheet.last_update,
                },
                ensure_ascii=False,
            ),
        }

    async def _handle_search_knowledge(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.knowledge_url:
            return {"success": False, "error": "Knowledge bridge not configured"}
        try:
            async with self._session.post(
                f"{self.knowledge_url}/api/knowledge/search",
                json={
                    "query": args.get("query", ""),
                    "source": args.get("source"),
                    "doc_type": args.get("doc_type"),
                    "tags": args.get("tags"),
                    "max_results": args.get("max_results", 5),
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_knowledge_sources(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.knowledge_url:
            return {"success": False, "error": "Knowledge bridge not configured"}
        try:
            async with self._session.get(
                f"{self.knowledge_url}/api/knowledge/sources",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_read_knowledge_document(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.knowledge_url:
            return {"success": False, "error": "Knowledge bridge not configured"}
        try:
            async with self._session.get(
                f"{self.knowledge_url}/api/knowledge/read",
                params={"source": args.get("source", ""), "path": args.get("path", "")},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_recent_knowledge_changes(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.knowledge_url:
            return {"success": False, "error": "Knowledge bridge not configured"}
        try:
            params: dict[str, Any] = {"limit": int(args.get("limit", 10))}
            source = args.get("source")
            if source:
                params["source"] = source
            async with self._session.get(
                f"{self.knowledge_url}/api/knowledge/recent",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}
