from typing import Any

import aiohttp
from loguru import logger

from brain_constants import backend_auth_headers
from tool_http import internal_headers


class CoreToolHandlers:
    async def _handle_create_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Create a task via DashboardClient and register with TaskQueueManager."""
        title = args.get("title", "")
        urgency = args.get("urgency", 2)
        zone = args.get("zone")

        result = await self.dashboard.create_task(args)

        if result and result.get("id"):
            task_id = result["id"]
            self.sanitizer.record_task_created()

            if self.task_queue:
                await self.task_queue.add_task(
                    task_id=task_id,
                    title=title,
                    urgency=urgency,
                    zone=zone,
                )

            self._capture_efficacy_baseline(task_id, title, zone)

            return {
                "success": True,
                "result": f"タスク '{title}' を作成しました (ID: {task_id})",
            }
        return {"success": False, "error": "タスクの作成に失敗しました"}

    def _capture_efficacy_baseline(self, task_id, title: str, zone) -> None:
        """Record a pending intervention-efficacy row for a measurable env task."""
        if not self.event_writer or not zone:
            return
        try:
            from efficacy import derive_trigger_metric

            metric = derive_trigger_metric(title)
            if metric is None:
                return
            zone_state = self.world_model.zones.get(zone)
            if zone_state is None:
                return
            baseline = getattr(zone_state.environment, metric, None)
            if baseline is None:
                return
            self.event_writer.record_intervention_created(
                task_id=task_id,
                zone=zone,
                trigger_metric=metric,
                baseline_value=float(baseline),
            )
        except Exception as e:
            logger.warning(f"efficacy baseline capture failed: {e}")

    async def _handle_speak(self, args: dict[str, Any]) -> dict[str, Any]:
        """Synthesize speech and record as ephemeral voice event."""
        raw_message = args.get("message", "")
        zone = args.get("zone", "")
        tone = args.get("tone", "neutral")
        skip_rewrite = bool(args.get("_skip_persona_rewrite", False))

        message = raw_message
        low_power = bool(self.power_mode_manager and self.power_mode_manager.is_low_power)
        vlm_swap = bool(getattr(self.world_model, "vlm_model_swap_active", False))
        if not skip_rewrite and self.persona_rewriter is not None and raw_message and not low_power and not vlm_swap:
            try:
                message = await self.persona_rewriter.rewrite(raw_message, tone=tone)
            except Exception as e:
                logger.debug(f"Persona rewrite failed, using raw: {e}")
                message = raw_message

        motion_id = None
        if self.motion_retriever:
            try:
                motion_id = self.motion_retriever.select(message, tone)
            except Exception as e:
                logger.warning(f"Motion retriever error: {e}")

        audio_url = None
        if self._session:
            try:
                async with self._session.post(
                    f"{self.voice_url}/api/voice/synthesize",
                    json={"text": message, "tone": tone},
                    headers=internal_headers(),
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        audio_url = data.get("audio_url")
                    else:
                        logger.warning(f"Voice synthesize failed: {resp.status}")
            except Exception as e:
                logger.warning(f"Voice synthesize error: {e}")

            try:
                await self._session.post(
                    f"{self.dashboard_api_url}/voice-events/",
                    json={
                        "message": message,
                        "audio_url": audio_url or "",
                        "zone": zone,
                        "tone": tone,
                        "motion_id": motion_id,
                    },
                    headers=backend_auth_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                )
            except Exception as e:
                logger.warning(f"Failed to record voice event: {e}")
        else:
            result = await self.dashboard.speak(message, zone, tone)
            if not result:
                return {"success": False, "error": "Speak failed"}

        self.sanitizer.record_speak(zone=zone or "general")
        return {
            "success": True,
            "result": f"「{message}」を音声で通知しました",
            "motion_id": motion_id,
        }

    async def _handle_get_active_tasks(self) -> dict[str, Any]:
        """Get active tasks from DashboardClient."""
        tasks = await self.dashboard.get_active_tasks()
        if not tasks:
            return {"success": True, "result": "アクティブなタスクはありません"}

        summaries = []
        for t in tasks[:10]:
            title = t.get("title", "")
            completed = t.get("is_completed", False)
            zone = t.get("zone", "")
            task_type = t.get("task_type", [])
            status_str = "完了" if completed else "対応中"
            zone_str = f", zone: {zone}" if zone else ""
            type_str = f", type: {','.join(task_type)}" if task_type else ""
            summaries.append(f"- {title} ({status_str}{zone_str}{type_str})")

        return {
            "success": True,
            "result": f"アクティブなタスク ({len(tasks)}件):\n" + "\n".join(summaries),
        }

    async def _handle_get_service_status(self, args: dict[str, Any]) -> dict[str, Any]:
        import json

        ss = self.world_model.services_state
        service_name = args.get("service_name")
        if service_name:
            svc = ss.services.get(service_name)
            if not svc:
                return {"success": False, "error": f"Service '{service_name}' not found"}
            status = {
                "name": svc.name,
                "available": svc.available,
                "unread_count": svc.unread_count,
                "summary": svc.summary,
                "last_check": svc.last_check,
                "error": svc.error,
            }
        else:
            status = {
                name: {
                    "name": svc.name,
                    "available": svc.available,
                    "unread_count": svc.unread_count,
                    "summary": svc.summary,
                    "last_check": svc.last_check,
                    "error": svc.error,
                }
                for name, svc in ss.services.items()
            }
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    async def _handle_add_shopping_item(self, args: dict[str, Any]) -> dict[str, Any]:
        """Add item to shopping list via backend API."""
        name = args.get("name", "")
        try:
            async with self._session.post(
                f"{self.dashboard_api_url}/shopping/",
                json={
                    "name": name,
                    "category": args.get("category"),
                    "quantity": args.get("quantity", 1),
                    "unit": args.get("unit"),
                    "store": args.get("store"),
                    "price": args.get("price"),
                    "is_recurring": args.get("is_recurring", False),
                    "recurrence_days": args.get("recurrence_days"),
                    "priority": args.get("priority", 1),
                    "created_by": "brain",
                },
                headers=backend_auth_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": f"買い物リストに「{name}」を追加しました"}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_shopping_list(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get shopping list from backend API."""
        params = {}
        if args.get("category"):
            params["category"] = args["category"]
        if args.get("store"):
            params["store"] = args["store"]
        try:
            async with self._session.get(
                f"{self.dashboard_api_url}/shopping/",
                params=params,
                headers=backend_auth_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    if not data:
                        return {"success": True, "result": "買い物リストは空です"}
                    items = []
                    for item in data[:15]:
                        name = item.get("name", "")
                        qty = item.get("quantity", 1)
                        cat = item.get("category", "")
                        store = item.get("store", "")
                        price = item.get("price")
                        parts = [f"- {name}"]
                        if qty > 1:
                            unit = item.get("unit", "個")
                            parts.append(f" x{qty}{unit}")
                        if cat:
                            parts.append(f" [{cat}]")
                        if store:
                            parts.append(f" @{store}")
                        if price:
                            parts.append(f" ¥{price}")
                        if item.get("is_recurring"):
                            parts.append(" (定期)")
                        items.append("".join(parts))
                    return {"success": True, "result": f"買い物リスト ({len(data)}件):\n" + "\n".join(items)}
                return {"success": False, "error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
