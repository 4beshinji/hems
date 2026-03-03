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
    CO2_HIGH, CO2_CRITICAL, TEMP_HIGH, TEMP_LOW, PC_GPU_TEMP_HIGH, PC_DISK_HIGH,
    SEDENTARY_MINUTES, HUMIDITY_HIGH, HUMIDITY_LOW, SPO2_LOW,
    HRV_LOW, BODY_TEMP_HIGH, RESPIRATORY_RATE_HIGH, SCREEN_TIME_ALERT_MINUTES,
    POWER_IDLE_WATTS, PM25_HIGH,
)

# Critical thresholds used only in low-power mode (more extreme than normal alerts)
TEMP_CRITICAL_HIGH = float(os.getenv("HEMS_THRESHOLD_TEMP_CRITICAL_HIGH", "40.0"))
TEMP_CRITICAL_LOW = float(os.getenv("HEMS_THRESHOLD_TEMP_CRITICAL_LOW", "5.0"))
SPO2_CRITICAL_LOW = int(os.getenv("HEMS_THRESHOLD_SPO2_CRITICAL_LOW", "88"))
HR_CRITICAL_SLEEP = int(os.getenv("HEMS_THRESHOLD_HR_CRITICAL_SLEEP", "150"))
from schedule_learner import ScheduleLearner


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

    COOLDOWN_SECONDS = 300  # 5 minutes

    def __init__(self, schedule_learner: ScheduleLearner | None = None):
        self.schedule_learner = schedule_learner
        self._cooldowns: dict[str, float] = {}
        self._pressure_history: dict[str, float] = {}  # zone_id → last known pressure

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

            # Humidity high
            if env.humidity is not None and env.humidity > HUMIDITY_HIGH:
                if self._check_cooldown(f"humidity_high_{zone_id}", now):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"{zone_id}の湿度が{env.humidity:.0f}%です。除湿しましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    })

            # Humidity low
            if env.humidity is not None and env.humidity < HUMIDITY_LOW:
                if self._check_cooldown(f"humidity_low_{zone_id}", now):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"{zone_id}の湿度が{env.humidity:.0f}%と低めです。加湿しましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    })

            # Pressure drop detection (weather pain / 気象病)
            if env.pressure is not None:
                prev_pressure = self._pressure_history.get(zone_id)
                self._pressure_history[zone_id] = env.pressure
                if prev_pressure is not None and prev_pressure - env.pressure >= 5:
                    if self._check_cooldown(f"pressure_drop_{zone_id}", now):
                        actions.append({
                            "tool": "speak",
                            "args": {
                                "message": f"気圧が低下しています（{prev_pressure:.0f}→{env.pressure:.0f}hPa）。頭痛に注意してください。",
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

        # --- Home Assistant rules ---
        hd = world_model.home_devices
        if hd.bridge_connected:
            actions.extend(self._evaluate_home_rules(world_model, now))
            actions.extend(self._evaluate_zigbee_sensor_rules(world_model, now))

        # --- Screen time rule ---
        st = world_model.user.screen_time
        if (st.total_minutes >= SCREEN_TIME_ALERT_MINUTES
                and self._check_cooldown("screen_time_alert", now)):
            hours = st.total_minutes // 60
            actions.append({
                "tool": "speak",
                "args": {
                    "message": f"画面を{hours}時間以上見ています。目を休めましょう。",
                    "zone": "home",
                    "tone": "caring",
                },
            })

        # --- Biometric rules ---
        bio = world_model.biometric_state
        if bio.bridge_connected:
            actions.extend(self._evaluate_biometric_rules(world_model, now))

        # --- Perception rules ---
        actions.extend(self._evaluate_perception_rules(world_model, now))

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

    def _evaluate_home_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate Home Assistant automation rules."""
        actions = []
        hd = world_model.home_devices
        hour = datetime.now().hour

        # --- 1. Sleep detection → lights off ---
        # Conditions: 23:00-5:00 AND idle AND static posture > 10 min AND lights on
        if (hour >= 23 or hour < 5):
            for zone_id, zone in world_model.zones.items():
                occ = zone.occupancy
                if (occ.count > 0
                        and occ.activity_class == "idle"
                        and occ.posture_status == "static"
                        and occ.posture_duration_sec > 600):
                    # Check if any lights are on
                    lights_on = [eid for eid, l in hd.lights.items() if l.on]
                    if lights_on and self._check_cooldown_daily(f"ha_sleep_detect_{zone_id}", now):
                        for eid in lights_on:
                            actions.append({
                                "tool": "control_light",
                                "args": {"entity_id": eid, "on": False},
                            })
                        actions.append({
                            "tool": "speak",
                            "args": {
                                "message": "おやすみなさい。照明を消しますね。",
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        })

        # --- 2. Pre-arrival HVAC ---
        # Conditions: nobody home AND predicted arrival in 30 min
        if self.schedule_learner:
            calendar_events = None
            if world_model.gas_state.bridge_connected:
                calendar_events = world_model.gas_state.calendar_events

            predicted_arrival = self.schedule_learner.predict_next_arrival(calendar_events)
            if predicted_arrival:
                minutes_until = (predicted_arrival - now) / 60
                all_away = all(z.occupancy.count == 0 for z in world_model.zones.values())

                if all_away and 0 < minutes_until <= 30:
                    if self._check_cooldown("ha_prearrival_hvac", now):
                        # Determine season from month
                        month = datetime.now().month
                        if 6 <= month <= 9:
                            mode, temp = "cool", 26
                        elif month <= 3 or month >= 11:
                            mode, temp = "heat", 22
                        else:
                            mode, temp = "auto", 24

                        for eid in hd.climates:
                            actions.append({
                                "tool": "control_climate",
                                "args": {"entity_id": eid, "mode": mode, "temperature": temp},
                            })
                        actions.append({
                            "tool": "speak",
                            "args": {
                                "message": f"もうすぐ帰宅ですね。エアコンを{mode}モード{temp}度でつけました。",
                                "zone": "home",
                                "tone": "caring",
                            },
                        })

        # --- 3. Wake-up curtain → natural light ---
        # Conditions: 60 min before predicted wake AND covers closed
        if self.schedule_learner:
            calendar_events = None
            if world_model.gas_state.bridge_connected:
                calendar_events = world_model.gas_state.calendar_events

            wake_time = self.schedule_learner.get_wake_time(calendar_events)
            if wake_time:
                minutes_until_wake = (wake_time - now) / 60
                if 0 < minutes_until_wake <= 60:
                    closed_covers = [eid for eid, c in hd.covers.items() if not c.is_open]
                    if closed_covers and self._check_cooldown_daily("ha_wake_curtain", now):
                        for eid in closed_covers:
                            actions.append({
                                "tool": "control_cover",
                                "args": {"entity_id": eid, "action": "open"},
                            })

        # --- 4. Wake-up detection → lights on + morning greeting ---
        # Conditions: 5:00-10:00 AND activity transitions from idle to low/moderate
        if 5 <= hour < 10:
            for zone_id, zone in world_model.zones.items():
                occ = zone.occupancy
                if (occ.count > 0
                        and occ.activity_class in ("low", "moderate", "high")
                        and self._check_cooldown_daily(f"ha_wake_detect_{zone_id}", now)):
                    lights_off = [eid for eid, l in hd.lights.items() if not l.on]
                    if lights_off:
                        for eid in lights_off:
                            actions.append({
                                "tool": "control_light",
                                "args": {"entity_id": eid, "on": True, "brightness": 255},
                            })
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": "おはようございます。",
                            "zone": zone_id,
                            "tone": "neutral",
                        },
                    })

        return actions

    def _evaluate_biometric_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate biometric health rules."""
        actions = []
        bio = world_model.biometric_state
        hour = datetime.now().hour

        # 1. High heart rate alert
        if (bio.heart_rate.bpm is not None and bio.heart_rate.bpm > 120
                and self._check_cooldown("bio_hr_high", now)):
            actions.append({
                "tool": "speak",
                "args": {
                    "message": f"心拍数が{bio.heart_rate.bpm}bpmです。少し休憩しましょう。",
                    "zone": "home",
                    "tone": "caring",
                },
            })

        # 2. High stress alert
        if (bio.stress.level > 80
                and bio.stress.last_update > 0
                and self._check_cooldown("bio_stress_high", now)):
            actions.append({
                "tool": "speak",
                "args": {
                    "message": "ストレスが高めです。深呼吸してリラックスしましょう。",
                    "zone": "home",
                    "tone": "caring",
                },
            })

        # 3. High fatigue alert
        if (bio.fatigue.score > 70
                and bio.fatigue.last_update > 0
                and self._check_cooldown("bio_fatigue_high", now)):
            if 21 <= hour <= 23:
                msg = "疲労が溜まっていますね。今日は早めに休みましょう。"
            else:
                msg = "疲れが溜まっていますね。少し休憩しましょう。"
            actions.append({
                "tool": "speak",
                "args": {"message": msg, "zone": "home", "tone": "caring"},
            })

        # 4. Poor sleep quality morning notification (8-10 AM)
        if (8 <= hour < 10
                and bio.sleep.quality_score > 0
                and bio.sleep.quality_score < 50
                and self._check_cooldown_daily("bio_sleep_poor", now)):
            actions.append({
                "tool": "speak",
                "args": {
                    "message": f"昨夜の睡眠品質が{bio.sleep.quality_score}点でした。今日は無理しないでくださいね。",
                    "zone": "home",
                    "tone": "caring",
                },
            })

        # 5. Step goal achievement
        if (bio.activity.steps > 0
                and bio.activity.steps_goal > 0
                and bio.activity.steps >= bio.activity.steps_goal
                and self._check_cooldown_daily("bio_steps_goal", now)):
            actions.append({
                "tool": "speak",
                "args": {
                    "message": f"歩数{bio.activity.steps}歩で目標達成です！お疲れさまでした！",
                    "zone": "home",
                    "tone": "humorous",
                },
            })

        # 6. Enhanced sleep detection (biometric + HA)
        # If sleep stage detected and HA connected, turn off lights
        hd = world_model.home_devices
        if (hd.bridge_connected
                and bio.sleep.stage in ("deep", "light", "rem")
                and self._check_cooldown_daily("bio_sleep_lights", now)):
            lights_on = [eid for eid, l in hd.lights.items() if l.on]
            if lights_on:
                for eid in lights_on:
                    actions.append({
                        "tool": "control_light",
                        "args": {"entity_id": eid, "on": False},
                    })
                actions.append({
                    "tool": "speak",
                    "args": {
                        "message": "おやすみなさい。照明を消しますね。",
                        "zone": "home",
                        "tone": "caring",
                    },
                })

        # 8. Low HRV alert (autonomic stress)
        if (bio.hrv.rmssd_ms is not None and bio.hrv.rmssd_ms < HRV_LOW
                and bio.hrv.last_update > 0
                and self._check_cooldown("bio_hrv_low", now)):
            actions.append({
                "tool": "speak",
                "args": {
                    "message": f"HRVが{bio.hrv.rmssd_ms}msと低めです。自律神経の疲れが出ています。",
                    "zone": "home",
                    "tone": "caring",
                },
            })

        # 9. Body temperature high
        if (bio.body_temperature.celsius is not None
                and bio.body_temperature.celsius > BODY_TEMP_HIGH
                and bio.body_temperature.last_update > 0
                and self._check_cooldown("bio_body_temp_high", now)):
            actions.append({
                "tool": "speak",
                "args": {
                    "message": f"体温が{bio.body_temperature.celsius:.1f}°Cです。体調に気をつけてください。",
                    "zone": "home",
                    "tone": "caring",
                },
            })

        # 10. Respiratory rate high
        if (bio.respiratory_rate.breaths_per_minute is not None
                and bio.respiratory_rate.breaths_per_minute > RESPIRATORY_RATE_HIGH
                and bio.respiratory_rate.last_update > 0
                and self._check_cooldown("bio_resp_high", now)):
            actions.append({
                "tool": "speak",
                "args": {
                    "message": "呼吸が速くなっています。落ち着いて深呼吸しましょう。",
                    "zone": "home",
                    "tone": "caring",
                },
            })

        # 11. Fatigue-linked dimming (21-23h, fatigue > 60, HA connected)
        if (hd.bridge_connected
                and 21 <= hour <= 23
                and bio.fatigue.score > 60
                and bio.fatigue.last_update > 0
                and self._check_cooldown("bio_fatigue_dim", now)):
            for eid, light in hd.lights.items():
                if light.on and light.brightness > 100:
                    actions.append({
                        "tool": "control_light",
                        "args": {
                            "entity_id": eid,
                            "on": True,
                            "brightness": 80,
                            "color_temp": 400,  # warm
                        },
                    })

        return actions

    def _evaluate_perception_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate camera/perception-based rules."""
        actions = []
        hour = datetime.now().hour
        ha_enabled = world_model.home_devices.bridge_connected

        for zone_id, zone in world_model.zones.items():
            occ = zone.occupancy

            # 1. Sedentary sitting detection (camera posture)
            if (occ.posture == "sitting"
                    and occ.posture_duration_sec > SEDENTARY_MINUTES * 60
                    and self._check_cooldown(f"percep_sitting_{zone_id}", now)):
                duration_min = int(occ.posture_duration_sec / 60)
                actions.append({
                    "tool": "speak",
                    "args": {
                        "message": f"{duration_min}分座りっぱなしです。少し体を動かしましょう。",
                        "zone": zone_id,
                        "tone": "caring",
                    },
                })

            # 2. Empty room with lights/climate on → turn off (HA required)
            if (ha_enabled
                    and occ.count == 0
                    and occ.last_update > 0
                    and now - occ.last_update < 300):
                hd = world_model.home_devices
                lights_on = [eid for eid, l in hd.lights.items()
                             if l.on and zone_id in eid]
                if lights_on and self._check_cooldown(f"percep_empty_lights_{zone_id}", now):
                    for eid in lights_on:
                        actions.append({
                            "tool": "control_light",
                            "args": {"entity_id": eid, "on": False},
                        })
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"{zone_id}は空室です。照明を消しますね。",
                            "zone": zone_id,
                            "tone": "neutral",
                        },
                    })
                climates_on = [eid for eid, c in hd.climates.items()
                               if c.mode != "off" and zone_id in eid]
                if climates_on and self._check_cooldown(f"percep_empty_climate_{zone_id}", now):
                    for eid in climates_on:
                        actions.append({
                            "tool": "control_climate",
                            "args": {"entity_id": eid, "mode": "off"},
                        })

            # 3. Daytime lying detection → health check
            if (6 <= hour <= 21
                    and occ.posture == "lying"
                    and occ.posture_duration_sec > 600
                    and self._check_cooldown(f"percep_lying_{zone_id}", now)):
                actions.append({
                    "tool": "speak",
                    "args": {
                        "message": "日中に横になっていますね。体調は大丈夫ですか？",
                        "zone": zone_id,
                        "tone": "caring",
                    },
                })

            # 4. Activity level sudden drop (>0.5 → <0.1 sustained 15min)
            if (occ.activity_level is not None
                    and occ.activity_level < 0.1
                    and occ.count > 0
                    and occ.posture_duration_sec > 900
                    and self._check_cooldown(f"percep_activity_drop_{zone_id}", now)):
                actions.append({
                    "tool": "speak",
                    "args": {
                        "message": "しばらく動きがないようです。大丈夫ですか？",
                        "zone": zone_id,
                        "tone": "caring",
                    },
                })

        return actions

    def _evaluate_zigbee_sensor_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate Zigbee binary_sensor and sensor rules."""
        actions = []
        hd = world_model.home_devices

        # --- Z1: Moisture emergency ---
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "moisture" and bs.state:
                if self._check_cooldown(f"zigbee_moisture_{eid}", now):
                    name = eid.split(".")[-1] if "." in eid else eid
                    actions.append({
                        "tool": "create_task",
                        "args": {
                            "title": f"【緊急】水漏れ検知: {name}",
                            "description": f"{name}で水漏れが検知されました。直ちに確認してください。",
                            "xp_reward": 200,
                            "urgency": 4,
                            "zone": "home",
                            "task_type": ["water_leak"],
                        },
                    })
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"緊急！{name}で水漏れを検知しました！すぐに確認してください！",
                            "zone": "home",
                            "tone": "alert",
                        },
                    })

        # --- Z2: Door arrival/departure ---
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "door" and not bs.state and bs.previous_state:
                # door closed transition (was open, now closed)
                if now - bs.last_changed > 60:
                    continue  # too old
                if self._check_cooldown(f"zigbee_door_{eid}", now):
                    # Check occupancy to determine arrival vs departure
                    any_occupied = any(
                        z.occupancy.count > 0 for z in world_model.zones.values()
                    )
                    if any_occupied:
                        # Arrival: turn on lights
                        actions.append({
                            "tool": "speak",
                            "args": {
                                "message": "おかえりなさい。",
                                "zone": "home",
                                "tone": "neutral",
                            },
                        })
                        lights_off = [lid for lid, l in hd.lights.items() if not l.on]
                        for lid in lights_off:
                            actions.append({
                                "tool": "control_light",
                                "args": {"entity_id": lid, "on": True},
                            })
                    else:
                        # Departure: turn off lights + switches
                        actions.append({
                            "tool": "speak",
                            "args": {
                                "message": "いってらっしゃい。照明とスイッチを切りますね。",
                                "zone": "home",
                                "tone": "neutral",
                            },
                        })
                        lights_on = [lid for lid, l in hd.lights.items() if l.on]
                        for lid in lights_on:
                            actions.append({
                                "tool": "control_light",
                                "args": {"entity_id": lid, "on": False},
                            })
                        switches_on = [sid for sid, v in hd.switches.items() if v]
                        for sid in switches_on:
                            actions.append({
                                "tool": "control_switch",
                                "args": {"entity_id": sid, "on": False},
                            })

        # --- Z3: Appliance finished (power drop to idle) ---
        for eid, s in hd.sensors.items():
            if s.device_class == "power" and s.previous_value > POWER_IDLE_WATTS and s.value <= POWER_IDLE_WATTS:
                if self._check_cooldown(f"zigbee_power_{eid}", now):
                    name = eid.split(".")[-1] if "." in eid else eid
                    name_lower = name.lower()
                    if any(w in name_lower for w in ("washing", "laundry", "washer", "洗濯")):
                        actions.append({
                            "tool": "create_task",
                            "args": {
                                "title": "洗濯物を干す",
                                "description": f"{name}の運転が完了しました。洗濯物を干してください。",
                                "xp_reward": 100,
                                "urgency": 2,
                                "zone": "home",
                                "task_type": ["laundry"],
                            },
                        })
                        actions.append({
                            "tool": "speak",
                            "args": {
                                "message": "洗濯が完了しました。洗濯物を干しましょう。",
                                "zone": "home",
                                "tone": "neutral",
                            },
                        })
                    elif any(w in name_lower for w in ("kettle", "ケトル", "pot")):
                        actions.append({
                            "tool": "speak",
                            "args": {
                                "message": "お湯が沸きました。",
                                "zone": "home",
                                "tone": "neutral",
                            },
                        })
                    else:
                        actions.append({
                            "tool": "speak",
                            "args": {
                                "message": f"{name}の運転が完了しました。",
                                "zone": "home",
                                "tone": "neutral",
                            },
                        })

        # --- Z4: CO2 high + all windows closed → ventilation suggestion ---
        co2_sensors = [s for s in hd.sensors.values() if s.device_class == "carbon_dioxide"]
        window_sensors = [bs for bs in hd.binary_sensors.values() if bs.device_class == "window"]
        for s in co2_sensors:
            if s.value > CO2_HIGH:
                all_closed = all(not ws.state for ws in window_sensors) if window_sensors else False
                if all_closed and self._check_cooldown(f"zigbee_co2_window_{s.entity_id}", now):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"CO2が{int(s.value)}ppmです。窓を開けて換気しましょう。",
                            "zone": "home",
                            "tone": "caring",
                        },
                    })

        # --- Z5: PM2.5 high → purifier on ---
        pm25_sensors = [s for s in hd.sensors.values() if s.device_class == "pm25"]
        for s in pm25_sensors:
            if s.value > PM25_HIGH:
                if self._check_cooldown(f"zigbee_pm25_{s.entity_id}", now):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"PM2.5が{int(s.value)}μg/m³です。空気清浄機をつけます。",
                            "zone": "home",
                            "tone": "caring",
                        },
                    })
                    # Turn on purifier switches
                    purifier_switches = [
                        sid for sid in hd.switches
                        if any(w in sid.lower() for w in ("purifier", "清浄", "air"))
                    ]
                    for sid in purifier_switches:
                        actions.append({
                            "tool": "control_switch",
                            "args": {"entity_id": sid, "on": True},
                        })

        # --- Z6: Vibration stopped (washing machine) ---
        for eid, bs in hd.binary_sensors.items():
            if (bs.device_class == "vibration"
                    and not bs.state and bs.previous_state):
                name_lower = eid.lower()
                if any(w in name_lower for w in ("washing", "laundry", "washer", "洗濯")):
                    if self._check_cooldown(f"zigbee_vibration_{eid}", now):
                        actions.append({
                            "tool": "create_task",
                            "args": {
                                "title": "洗濯物を干す",
                                "description": "洗濯機の振動が停止しました。洗濯物を干してください。",
                                "xp_reward": 100,
                                "urgency": 2,
                                "zone": "home",
                                "task_type": ["laundry"],
                            },
                        })
                        actions.append({
                            "tool": "speak",
                            "args": {
                                "message": "洗濯機が止まりました。洗濯物を干しましょう。",
                                "zone": "home",
                                "tone": "neutral",
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

    def evaluate_critical(self, world_model) -> list[dict]:
        """Evaluate life-safety critical rules only.

        Used in low-power mode (sleep / away) to respond to dangerous conditions
        without running the full rule set or the LLM.  Only fires on conditions
        that genuinely require immediate action regardless of occupancy or time.
        """
        actions = []
        now = time.time()

        # --- Environmental: CO2 danger level ---
        for zone_id, zone in world_model.zones.items():
            env = zone.environment
            if (env.co2 is not None and env.co2 > CO2_CRITICAL
                    and self._check_cooldown(f"critical_co2_{zone_id}", now)):
                actions.append({
                    "tool": "create_task",
                    "args": {
                        "title": f"【緊急】{zone_id}のCO2危険レベル",
                        "description": (
                            f"CO2濃度が{int(env.co2)}ppmです。直ちに換気してください。"
                        ),
                        "xp_reward": 200,
                        "urgency": 5,
                        "zone": zone_id,
                        "task_type": ["ventilation"],
                    },
                })
                actions.append({
                    "tool": "speak",
                    "args": {
                        "message": (
                            f"緊急です！{zone_id}のCO2濃度が{int(env.co2)}ppmです。"
                            "すぐに換気してください！"
                        ),
                        "zone": zone_id,
                        "tone": "urgent",
                    },
                })

            # --- Environmental: extreme temperature ---
            if env.temperature is not None:
                if (env.temperature > TEMP_CRITICAL_HIGH
                        and self._check_cooldown(f"critical_temp_high_{zone_id}", now)):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": (
                                f"危険！{zone_id}の室温が{env.temperature:.1f}℃です。"
                                "熱中症に注意してください！"
                            ),
                            "zone": zone_id,
                            "tone": "urgent",
                        },
                    })
                elif (env.temperature < TEMP_CRITICAL_LOW
                        and self._check_cooldown(f"critical_temp_low_{zone_id}", now)):
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": (
                                f"危険！{zone_id}の室温が{env.temperature:.1f}℃まで低下しています。"
                                "暖房を確認してください！"
                            ),
                            "zone": zone_id,
                            "tone": "urgent",
                        },
                    })

        # --- Zigbee: Moisture emergency (water leak) ---
        hd = world_model.home_devices
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "moisture" and bs.state:
                if self._check_cooldown(f"critical_moisture_{eid}", now):
                    name = eid.split(".")[-1] if "." in eid else eid
                    actions.append({
                        "tool": "create_task",
                        "args": {
                            "title": f"【緊急】水漏れ検知: {name}",
                            "description": f"{name}で水漏れが検知されました。直ちに確認してください。",
                            "xp_reward": 200,
                            "urgency": 4,
                            "zone": "home",
                            "task_type": ["water_leak"],
                        },
                    })
                    actions.append({
                        "tool": "speak",
                        "args": {
                            "message": f"緊急！{name}で水漏れを検知しました！すぐに確認してください！",
                            "zone": "home",
                            "tone": "urgent",
                        },
                    })

        # --- Biometric: SpO2 critical drop (sleep apnea risk) ---
        bio = world_model.biometric_state
        if (bio.spo2.percent is not None
                and bio.spo2.percent < SPO2_CRITICAL_LOW
                and bio.spo2.last_update > now - 300
                and self._check_cooldown("critical_spo2", now)):
            actions.append({
                "tool": "speak",
                "args": {
                    "message": (
                        f"緊急！血中酸素濃度が{bio.spo2.percent}%まで低下しています！"
                        "目を覚ましてください！"
                    ),
                    "zone": "home",
                    "tone": "urgent",
                },
            })

        # --- Biometric: very high heart rate during sleep ---
        if (bio.heart_rate.bpm is not None
                and bio.heart_rate.bpm > HR_CRITICAL_SLEEP
                and bio.sleep.stage in ("deep", "light", "rem")
                and bio.heart_rate.last_update > now - 120
                and self._check_cooldown("critical_hr_sleep", now)):
            actions.append({
                "tool": "speak",
                "args": {
                    "message": (
                        f"睡眠中に心拍数が{bio.heart_rate.bpm}bpmに達しています！"
                        "体調を確認してください！"
                    ),
                    "zone": "home",
                    "tone": "urgent",
                },
            })

        return actions
