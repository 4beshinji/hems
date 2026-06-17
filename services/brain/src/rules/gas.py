"""Domain-specific RuleEngine rules.

Extracted as a mixin to keep RuleEngine public methods stable.
"""

from datetime import datetime


class GasRulesMixin:
    def _evaluate_gas_rules(self, gas, now: float, world_model=None) -> list[dict]:
        """Evaluate GAS-related rules. Returns list of tool call actions."""
        actions = []

        local_now = datetime.now()
        hour = local_now.hour
        weekday = local_now.weekday()  # 0=Monday, 6=Sunday

        # --- Calendar rules ---

        # 1. Meeting reminder — 10 min before event
        for ev in gas.calendar_events:
            if ev.is_all_day or ev.start_ts <= 0:
                continue
            minutes_until = (ev.start_ts - now) / 60
            if 0 < minutes_until <= 10:
                key = f"gas_meeting_remind_{ev.id}"
                if self._check_cooldown(key, now):
                    msg = f"あと{int(minutes_until)}分で「{ev.title}」が始まります。"
                    if ev.location:
                        msg += f"（{ev.location}）"
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {"message": msg[:70], "zone": "home", "tone": "alert"},
                        }
                    )

        # 1b. Meeting prep — 30 min before event (speak + dim lights + 静音推奨)
        for ev in gas.calendar_events:
            if ev.is_all_day or ev.start_ts <= 0:
                continue
            minutes_until = (ev.start_ts - now) / 60
            # 25-30 min window so the rule fires reliably even with 30s cycle
            if 25 < minutes_until <= 30:
                key = f"gas_meeting_prep_{ev.id}"
                if self._check_cooldown_custom(key, now, 3600):
                    msg = f"30分後に「{ev.title}」があります。準備をお勧めします。"
                    if ev.location:
                        msg += f"（{ev.location}）"
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {"message": msg[:70], "zone": "home", "tone": "caring"},
                        }
                    )
                    # Dim lights to 70% in any zone with active light to encourage focus.
                    # Cap at first 2 lights to avoid wholesale changes.
                    dimmed = 0
                    for d in self._device_cache:
                        if dimmed >= 2:
                            break
                        caps = d.get("capabilities") or []
                        if "set_brightness" not in caps:
                            continue
                        if not d.get("is_enabled", True):
                            continue
                        last_state = d.get("last_state") or {}
                        if not last_state.get("on"):
                            continue
                        actions.append(
                            self._make_action(
                                d["device_id"],
                                "set_brightness",
                                {"brightness": 178},  # 70% of 255
                            )
                        )
                        dimmed += 1

        # 2. Overlapping events detection
        timed_events = [e for e in gas.calendar_events if not e.is_all_day and e.start_ts > 0]
        for i, ev1 in enumerate(timed_events):
            for ev2 in timed_events[i + 1 :]:
                if ev1.start_ts < ev2.end_ts and ev2.start_ts < ev1.end_ts:
                    key = f"gas_overlap_{ev1.id}_{ev2.id}"
                    if self._check_cooldown(key, now):
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"予定が重複しています: 「{ev1.title}」と「{ev2.title}」",
                                    "zone": "home",
                                    "tone": "alert",
                                },
                            }
                        )

        # 3. Morning briefing — 8:00-9:00, once per day
        if 8 <= hour < 9 and self._check_cooldown_daily("gas_morning_brief", now):
            event_count = len(gas.calendar_events)
            pending_tasks = [t for t in gas.tasks if t.status != "completed"]
            overdue = [t for t in gas.tasks if t.is_overdue]
            inbox = gas.gmail_labels.get("INBOX")
            unread = inbox.unread if inbox else 0
            msg = f"おはようございます。今日の予定{event_count}件"
            if pending_tasks:
                msg += f"、タスク{len(pending_tasks)}件"
            if overdue:
                msg += f"（期限切れ{len(overdue)}件）"
            if unread > 0:
                msg += f"、未読{unread}通"
            msg += "です。"
            actions.append(
                {
                    "tool": "speak",
                    "args": {"message": msg[:70], "zone": "home", "tone": "neutral"},
                }
            )

        # 4. Evening summary — 21:00-22:00, once per day
        if 21 <= hour < 22 and self._check_cooldown_daily("gas_evening_summary", now):
            # Look for tomorrow's first event
            tomorrow_start = now + (24 - hour) * 3600
            tomorrow_end = tomorrow_start + 24 * 3600
            tomorrow_events = [
                e for e in gas.calendar_events if not e.is_all_day and tomorrow_start <= e.start_ts < tomorrow_end
            ]
            if tomorrow_events:
                first = tomorrow_events[0]
                t_str = first.start.split("T")[1][:5] if "T" in first.start else "?"
                msg = f"明日は{len(tomorrow_events)}件の予定があります。最初は{t_str}「{first.title}」です。"
            else:
                msg = "明日の予定はありません。ゆっくり休んでください。"
            actions.append(
                {
                    "tool": "speak",
                    "args": {"message": msg[:70], "zone": "home", "tone": "caring"},
                }
            )

        # 5. Long free slot detection — 9:00-18:00, 2h+ free slots
        if 9 <= hour < 18:
            long_slots = [s for s in gas.free_slots if s.duration_minutes >= 120]
            for slot in long_slots[:1]:  # Only notify about first long slot
                key = f"gas_free_slot_{slot.start[:13]}"
                if self._check_cooldown(key, now):
                    t_str = slot.start.split("T")[1][:5] if "T" in slot.start else "?"
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{t_str}から{slot.duration_minutes}分の空き時間があります。集中作業に最適です。",
                                "zone": "home",
                                "tone": "neutral",
                            },
                        }
                    )

        # 6. Early bedtime suggestion — tomorrow's first event before 8:00
        if hour == 22:
            tomorrow_start = now + 2 * 3600  # ~midnight
            early_cutoff = tomorrow_start + 8 * 3600  # ~8:00 tomorrow
            early_events = [
                e for e in gas.calendar_events if not e.is_all_day and tomorrow_start <= e.start_ts < early_cutoff
            ]
            if early_events and self._check_cooldown_daily("gas_early_bed", now):
                first = early_events[0]
                t_str = first.start.split("T")[1][:5] if "T" in first.start else "?"
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"明日は{t_str}に予定があります。早めに休みましょう。",
                            "zone": "home",
                            "tone": "caring",
                        },
                    }
                )

        # --- Task rules ---

        # 7. Overdue task alert — staged escalation
        overdue_tasks = [t for t in gas.tasks if t.is_overdue]
        if overdue_tasks:
            # Stage A — initial info speak (1 per day, summary)
            if self._check_cooldown_daily("gas_overdue_alert", now):
                names = ", ".join(t.title[:15] for t in overdue_tasks[:3])
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"期限切れのタスクが{len(overdue_tasks)}件あります: {names}",
                            "zone": "home",
                            "tone": "alert",
                        },
                    }
                )

            # Stage B/C — per-task escalation based on hours overdue
            _dt = datetime

            for task in overdue_tasks:
                if not task.due or not task.id:
                    continue
                try:
                    due_dt = _dt.fromisoformat(task.due.replace("Z", "+00:00"))
                    hours_overdue = (now - due_dt.timestamp()) / 3600
                except (ValueError, AttributeError):
                    continue

                # Stage B (≥24h overdue): bump priority, alert
                if hours_overdue >= 24:
                    key_b = f"gas_overdue_24h_{task.id}"
                    if self._check_cooldown_custom(key_b, now, 86400):
                        actions.append(
                            {
                                "tool": "create_task",
                                "args": {
                                    "title": f"【優先】期限超過 {int(hours_overdue / 24)}日: {task.title[:40]}",
                                    "description": (
                                        f"Googleタスク「{task.title}」が{int(hours_overdue)}時間超過しています。"
                                        f"対応または再スケジュールを検討してください。"
                                    ),
                                    "urgency": 4,
                                    "zone": "home",
                                    "task_type": ["overdue_escalation"],
                                },
                            }
                        )

                # Stage C (≥72h overdue): suggest deletion
                if hours_overdue >= 72:
                    key_c = f"gas_overdue_72h_{task.id}"
                    if self._check_cooldown_custom(key_c, now, 7 * 86400):
                        actions.append(
                            {
                                "tool": "create_task",
                                "args": {
                                    "title": f"【削除候補】3日超過: {task.title[:40]}",
                                    "description": (
                                        f"「{task.title}」が72時間以上超過。実施意志がない場合は削除を検討。"
                                    ),
                                    "urgency": 2,
                                    "zone": "home",
                                    "task_type": ["delete_candidate"],
                                },
                            }
                        )

        # 8. Daily task sync — 8:00-10:00, sync Google Tasks to HEMS tasks
        if 8 <= hour < 10 and self._check_cooldown_daily("gas_task_sync", now):
            pending = [t for t in gas.tasks if t.status != "completed" and t.due]
            for task in pending[:3]:
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": f"[Google] {task.title}",
                            "description": f"Google Tasks: {task.notes}"
                            if task.notes
                            else f"Google Tasksから同期: {task.title}",
                            "urgency": 3 if task.is_overdue else 2,
                            "zone": "home",
                            "task_type": ["google_tasks"],
                        },
                    }
                )

        # --- Gmail rules ---

        inbox = gas.gmail_labels.get("INBOX")
        if inbox:
            # 9. Unread alert — 10+ unread
            if inbox.unread >= 10 and self._check_cooldown("gas_gmail_unread", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"未読メールが{inbox.unread}通あります。確認しましょう。",
                            "zone": "home",
                            "tone": "neutral",
                        },
                    }
                )

            # 10. Unread critical — 20+ unread
            if inbox.unread >= 20 and self._check_cooldown("gas_gmail_critical", now):
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": "メール整理",
                            "description": f"未読メールが{inbox.unread}通溜まっています。整理してください。",
                            "urgency": 2,
                            "zone": "home",
                            "task_type": ["email"],
                        },
                    }
                )

        # --- Drive rules ---

        # 11. Document update notification
        doc_types = {
            "application/vnd.google-apps.document": "ドキュメント",
            "application/vnd.google-apps.spreadsheet": "スプレッドシート",
            "application/vnd.google-apps.presentation": "スライド",
        }
        for f in gas.drive_recent[:5]:
            if f.mime_type in doc_types:
                key = f"gas_drive_{f.name[:20]}_{f.modified_time[:10]}"
                if self._check_cooldown(key, now):
                    type_name = doc_types[f.mime_type]
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{type_name}「{f.name[:20]}」が更新されました。",
                                "zone": "home",
                                "tone": "neutral",
                            },
                        }
                    )
                    break  # Only one drive notification per cycle

        # --- Sheets rules ---

        # 12. Threshold monitoring — sheets with metric/value/threshold columns
        for name, sheet in gas.sheets.items():
            if not sheet.headers or not sheet.values:
                continue
            headers_lower = [h.lower() for h in sheet.headers]
            try:
                metric_idx = next(i for i, h in enumerate(headers_lower) if h in ("metric", "項目", "name"))
                value_idx = next(i for i, h in enumerate(headers_lower) if h in ("value", "値", "actual"))
                threshold_idx = next(i for i, h in enumerate(headers_lower) if h in ("threshold", "閾値", "limit"))
            except StopIteration:
                continue  # Sheet doesn't have required columns

            for row in sheet.values:
                if len(row) <= max(metric_idx, value_idx, threshold_idx):
                    continue
                try:
                    metric_name = str(row[metric_idx])
                    value = float(row[value_idx])
                    threshold = float(row[threshold_idx])
                except (ValueError, TypeError):
                    continue

                if value > threshold:
                    key = f"gas_sheet_{name}_{metric_name}"
                    if self._check_cooldown(key, now):
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"[{name}] {metric_name}が閾値超過: {value} > {threshold}",
                                    "zone": "home",
                                    "tone": "alert",
                                },
                            }
                        )

        # --- Weekly rules ---

        # 13. Weekly review — Sunday 18:00-20:00
        if weekday == 6 and 18 <= hour < 20:
            if self._check_cooldown_daily("gas_weekly_review", now):
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": "週次レビュー",
                            "description": "今週の振り返りと来週の計画を立てましょう。",
                            "urgency": 2,
                            "zone": "home",
                            "task_type": ["review"],
                        },
                    }
                )

        # Urgent news notification
        if hasattr(world_model, "news_state"):
            ns = world_model.news_state
            for article in ns.urgent_articles:
                url_key = article.get("url", "")[:50]
                if url_key and self._check_cooldown(f"news_urgent_{url_key}", now):
                    title = article.get("title", "")[:50]
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"速報です。{title}",
                                "zone": "home",
                                "tone": "alert",
                            },
                        }
                    )

        return actions
