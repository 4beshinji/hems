"""
Rule-based fallback engine for HEMS Brain.
Used when GPU load is high or LLM is unavailable.
Evaluates simple threshold rules and returns tool call actions.
"""
import os
import subprocess
import time
from datetime import datetime, timezone
from loguru import logger
from world_model.world_model import (
    CO2_HIGH, TEMP_HIGH, TEMP_LOW, PC_GPU_TEMP_HIGH, PC_DISK_HIGH,
    SEDENTARY_MINUTES,
)


GPU_TYPE = os.getenv("GPU_TYPE", "none")  # amd | nvidia | none
GPU_HIGH_LOAD_THRESHOLD = int(os.getenv("GPU_HIGH_LOAD_THRESHOLD", "80"))


def _get_gpu_utilization() -> float | None:
    """Query GPU utilization percentage. Returns None if unavailable."""
    try:
        if GPU_TYPE == "nvidia":
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                timeout=5, text=True,
            )
            return float(out.strip().split("\n")[0])
        elif GPU_TYPE == "amd":
            out = subprocess.check_output(
                ["rocm-smi", "--showuse", "--csv"],
                timeout=5, text=True,
            )
            for line in out.strip().split("\n"):
                if "," in line and not line.startswith("device"):
                    parts = line.split(",")
                    if len(parts) >= 2:
                        try:
                            return float(parts[1].strip().replace("%", ""))
                        except ValueError:
                            pass
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError) as e:
        logger.debug(f"GPU query failed: {e}")
    return None


class RuleEngine:
    """Threshold-based decision engine — no LLM required."""

    # Cooldowns to prevent repeated actions (zone -> last_action_time)
    _cooldowns: dict[str, float] = {}
    COOLDOWN_SECONDS = 300  # 5 minutes

    def should_use_rules(self) -> bool:
        """Check if we should use rule-based mode instead of LLM."""
        if GPU_TYPE == "none":
            return False
        util = _get_gpu_utilization()
        if util is not None and util > GPU_HIGH_LOAD_THRESHOLD:
            return True
        return False

    def evaluate(self, world_model) -> list[dict]:
        """Evaluate rules against current world state. Returns list of tool call actions."""
        actions = []
        now = time.time()

        for zone_id, zone in world_model.zones.items():
            env = zone.environment

            # CO2 above threshold -> create ventilation task
            if env.co2 is not None and env.co2 > CO2_HIGH:
                if self._check_cooldown(f"co2_{zone_id}", now):
                    actions.append({
                        "tool": "create_task",
                        "args": {
                            "title": f"{zone_id}の換気",
                            "description": f"CO2濃度が{int(env.co2)}ppmです。窓を開けて換気してください。",
                            "xp_reward": 100,
                            "urgency": 3,
                            "zone": zone_id,
                            "task_type": ["ventilation"],
                        },
                    })

            # Temperature too high or too low
            if env.temperature is not None:
                if env.temperature > TEMP_HIGH and self._check_cooldown(f"temp_high_{zone_id}", now):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"{zone_id}の室温が{env.temperature:.1f}度です。エアコンをつけましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    })
                elif env.temperature < TEMP_LOW and self._check_cooldown(f"temp_low_{zone_id}", now):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"{zone_id}の室温が{env.temperature:.1f}度と低めです。暖房をつけましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    })

            # Sedentary detection (from events)
            for event in zone.events:
                if event.event_type == "sedentary_alert" and self._check_cooldown(f"sed_{zone_id}", now):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": "長時間座っていますね。少し休憩しましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    })

            # Long static posture detection
            occ = zone.occupancy
            if (occ.posture_status == "static"
                    and occ.posture_duration_sec > SEDENTARY_MINUTES * 60
                    and self._check_cooldown(f"posture_{zone_id}", now)):
                duration_min = int(occ.posture_duration_sec / 60)
                actions.append({
                    "tool": "speak",
                    "args": {
                        "message": f"同じ姿勢で{duration_min}分経っています。少しストレッチしましょう。",
                        "zone": zone_id,
                        "tone": "caring",
                    },
                })

            # Late night low activity — suggest sleep
            hour = datetime.now().hour
            if ((hour >= 23 or hour < 5)
                    and occ.activity_class == "idle"
                    and occ.count > 0
                    and self._check_cooldown(f"late_idle_{zone_id}", now)):
                actions.append({
                    "tool": "speak",
                    "args": {
                        "message": "深夜ですね。そろそろ休みましょう。",
                        "zone": zone_id,
                        "tone": "caring",
                    },
                })

        # --- PC rules ---
        pc = world_model.pc_state
        if pc.gpu.temp_c > PC_GPU_TEMP_HIGH and self._check_cooldown("pc_gpu_hot", now):
            actions.append({
                "tool": "speak",
                "args": {
                    "message": f"GPU温度が{pc.gpu.temp_c:.0f}度です。負荷を下げてください。",
                    "zone": "pc",
                    "tone": "alert",
                },
            })

        if pc.disk.partitions:
            for p in pc.disk.partitions:
                if p.percent > PC_DISK_HIGH and self._check_cooldown(f"pc_disk_{p.mount}", now):
                    actions.append({
                        "tool": "create_task",
                        "args": {
                            "title": f"ディスク容量不足: {p.mount}",
                            "description": f"{p.mount}の使用率が{p.percent:.0f}%です。不要ファイルを削除してください。",
                            "xp_reward": 100,
                            "urgency": 2,
                            "zone": "pc",
                            "task_type": ["maintenance"],
                        },
                    })

        # --- GAS rules ---
        gas = world_model.gas_state
        if gas.bridge_connected:
            actions.extend(self._evaluate_gas_rules(gas, now))

        return actions

    def _evaluate_gas_rules(self, gas, now: float) -> list[dict]:
        """Evaluate GAS-related rules. Returns list of tool call actions."""
        actions = []

        try:
            local_now = datetime.now()
        except Exception:
            local_now = datetime.now(timezone.utc)
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
                    actions.append({
                        "tool": "speak",
                        "args": {"message": msg[:70], "zone": "home", "tone": "alert"},
                    })

        # 2. Overlapping events detection
        timed_events = [e for e in gas.calendar_events if not e.is_all_day and e.start_ts > 0]
        for i, ev1 in enumerate(timed_events):
            for ev2 in timed_events[i + 1:]:
                if ev1.start_ts < ev2.end_ts and ev2.start_ts < ev1.end_ts:
                    key = f"gas_overlap_{ev1.id}_{ev2.id}"
                    if self._check_cooldown(key, now):
                        actions.append({
                            "tool": "speak",
                            "args": {
                                "message": f"予定が重複しています: 「{ev1.title}」と「{ev2.title}」",
                                "zone": "home", "tone": "alert",
                            },
                        })

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
            actions.append({
                "tool": "speak",
                "args": {"message": msg[:70], "zone": "home", "tone": "neutral"},
            })

        # 4. Evening summary — 21:00-22:00, once per day
        if 21 <= hour < 22 and self._check_cooldown_daily("gas_evening_summary", now):
            # Look for tomorrow's first event
            tomorrow_start = now + (24 - hour) * 3600
            tomorrow_end = tomorrow_start + 24 * 3600
            tomorrow_events = [
                e for e in gas.calendar_events
                if not e.is_all_day and tomorrow_start <= e.start_ts < tomorrow_end
            ]
            if tomorrow_events:
                first = tomorrow_events[0]
                t_str = first.start.split("T")[1][:5] if "T" in first.start else "?"
                msg = f"明日は{len(tomorrow_events)}件の予定があります。最初は{t_str}「{first.title}」です。"
            else:
                msg = "明日の予定はありません。ゆっくり休んでください。"
            actions.append({
                "tool": "speak",
                "args": {"message": msg[:70], "zone": "home", "tone": "caring"},
            })

        # 5. Long free slot detection — 9:00-18:00, 2h+ free slots
        if 9 <= hour < 18:
            long_slots = [s for s in gas.free_slots if s.duration_minutes >= 120]
            for slot in long_slots[:1]:  # Only notify about first long slot
                key = f"gas_free_slot_{slot.start[:13]}"
                if self._check_cooldown(key, now):
                    t_str = slot.start.split("T")[1][:5] if "T" in slot.start else "?"
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"{t_str}から{slot.duration_minutes}分の空き時間があります。集中作業に最適です。",
                            "zone": "home", "tone": "neutral",
                        },
                    })

        # 6. Early bedtime suggestion — tomorrow's first event before 8:00
        if hour == 22:
            tomorrow_start = now + 2 * 3600  # ~midnight
            early_cutoff = tomorrow_start + 8 * 3600  # ~8:00 tomorrow
            early_events = [
                e for e in gas.calendar_events
                if not e.is_all_day and tomorrow_start <= e.start_ts < early_cutoff
            ]
            if early_events and self._check_cooldown_daily("gas_early_bed", now):
                first = early_events[0]
                t_str = first.start.split("T")[1][:5] if "T" in first.start else "?"
                actions.append({
                    "tool": "speak",
                    "args": {
                        "message": f"明日は{t_str}に予定があります。早めに休みましょう。",
                        "zone": "home", "tone": "caring",
                    },
                })

        # --- Task rules ---

        # 7. Overdue task alert
        overdue_tasks = [t for t in gas.tasks if t.is_overdue]
        if overdue_tasks and self._check_cooldown("gas_overdue_alert", now):
            names = ", ".join(t.title[:15] for t in overdue_tasks[:3])
            actions.append({
                "tool": "speak",
                "args": {
                    "message": f"期限切れのタスクが{len(overdue_tasks)}件あります: {names}",
                    "zone": "home", "tone": "alert",
                },
            })

        # 8. Daily task sync — 8:00-10:00, sync Google Tasks to HEMS tasks
        if 8 <= hour < 10 and self._check_cooldown_daily("gas_task_sync", now):
            pending = [t for t in gas.tasks if t.status != "completed" and t.due]
            for task in pending[:3]:
                actions.append({
                    "tool": "create_task",
                    "args": {
                        "title": f"[Google] {task.title}",
                        "description": f"Google Tasks: {task.notes}" if task.notes else f"Google Tasksから同期: {task.title}",
                        "xp_reward": 50,
                        "urgency": 3 if task.is_overdue else 2,
                        "zone": "home",
                        "task_type": ["google_tasks"],
                    },
                })

        # --- Gmail rules ---

        inbox = gas.gmail_labels.get("INBOX")
        if inbox:
            # 9. Unread alert — 10+ unread
            if inbox.unread >= 10 and self._check_cooldown("gas_gmail_unread", now):
                actions.append({
                    "tool": "speak",
                    "args": {
                        "message": f"未読メールが{inbox.unread}通あります。確認しましょう。",
                        "zone": "home", "tone": "neutral",
                    },
                })

            # 10. Unread critical — 20+ unread
            if inbox.unread >= 20 and self._check_cooldown("gas_gmail_critical", now):
                actions.append({
                    "tool": "create_task",
                    "args": {
                        "title": "メール整理",
                        "description": f"未読メールが{inbox.unread}通溜まっています。整理してください。",
                        "xp_reward": 100,
                        "urgency": 2,
                        "zone": "home",
                        "task_type": ["email"],
                    },
                })

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
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"{type_name}「{f.name[:20]}」が更新されました。",
                            "zone": "home", "tone": "neutral",
                        },
                    })
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
                        actions.append({
                            "tool": "speak",
                            "args": {
                                "message": f"[{name}] {metric_name}が閾値超過: {value} > {threshold}",
                                "zone": "home", "tone": "alert",
                            },
                        })

        # --- Weekly rules ---

        # 13. Weekly review — Sunday 18:00-20:00
        if weekday == 6 and 18 <= hour < 20:
            if self._check_cooldown_daily("gas_weekly_review", now):
                actions.append({
                    "tool": "create_task",
                    "args": {
                        "title": "週次レビュー",
                        "description": "今週の振り返りと来週の計画を立てましょう。",
                        "xp_reward": 200,
                        "urgency": 2,
                        "zone": "home",
                        "task_type": ["review"],
                    },
                })

        return actions

    def _check_cooldown(self, key: str, now: float) -> bool:
        """Check and set cooldown. Returns True if action is allowed."""
        last = self._cooldowns.get(key, 0)
        if now - last < self.COOLDOWN_SECONDS:
            return False
        self._cooldowns[key] = now
        return True

    def _check_cooldown_daily(self, key: str, now: float) -> bool:
        """Check and set daily cooldown (24h). Returns True if action is allowed."""
        last = self._cooldowns.get(key, 0)
        if now - last < 86400:  # 24 hours
            return False
        self._cooldowns[key] = now
        return True
