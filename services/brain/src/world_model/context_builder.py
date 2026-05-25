"""WorldModel mixin extracted from the facade module."""

from . import world_model as _world_model


class ContextBuilderMixin:
    def get_llm_context(self) -> str:
        """Build text context for LLM from current world state (tri-domain)."""
        sections = []

        physical = self._get_physical_context()
        if physical:
            sections.append("## 現実空間\n" + physical)

        digital = self._get_digital_context()
        if digital:
            sections.append("## 電子空間\n" + digital)

        user = self._get_user_context()
        if user:
            sections.append("## ユーザー状態\n" + user)

        return "\n\n".join(sections)

    def is_blind(self, threshold_sec: float = _world_model.ZONE_BLIND_SEC) -> bool:
        """Whether the system has lost fresh perception (degraded operation).

        Returns True when there are no zones at all, or every known zone has
        gone quiet (no sensor update) for longer than ``threshold_sec``. The
        cognitive loop consults this to drop into observe-only mode: it keeps
        observing and speaking, but suppresses side-effecting tools so it never
        actuates the home or files environment-response tasks on a stale view.
        """
        if not self.zones:
            return True
        now = _world_model.time.time()
        return all(
            z.environment.last_update == 0 or (now - z.environment.last_update) > threshold_sec
            for z in self.zones.values()
        )

    def _stale_note(self, env, channel: str, now: float) -> str:
        """Inline age suffix for a stale channel reading, else ''."""
        ts = env.channel_last_seen.get(channel)
        if ts is None:
            return ""
        age = now - ts
        if age > _world_model.ENV_STALE_SEC:
            return f"（{int(age / 60)}分前・古い）"
        return ""

    def _get_physical_context(self) -> str:
        """Build physical space context (zones + smart home)."""
        lines = []
        now = _world_model.time.time()

        # VLM model swap banner — brain is in rule-based fallback during heavy load
        if getattr(self, "vlm_model_swap_active", False):
            lines.append("### ⚠ VLMモデル切替中\n  重量モデルがVRAM占有中 — brainはrule-basedモード")

        # Trend arrows for analog channels
        _TREND = {"rising": "↑", "falling": "↓", "stable": ""}

        # Zone data
        for zone_id, zone in self.zones.items():
            env = zone.environment
            parts = [f"### {zone_id}"]

            # Degraded operation: flag a zone whose sensors have gone quiet, so
            # the LLM knows the readings below may be stale (and the blind guard
            # may be suppressing side-effects).
            if env.last_update > 0 and (now - env.last_update) > _world_model.ENV_STALE_SEC:
                parts.append(f"  ⚠️ データ更新なし（最終更新 {int((now - env.last_update) / 60)}分前・古い）")

            def _t(ch: str, env=env) -> str:
                return _TREND.get(env.trends.get(ch, "stable"), "")

            # Fused sensor summary — one line per zone, priority order
            # (temp, hum, pressure, voc, pm25, light, soil). Skips None channels,
            # truncates to 140 chars.
            summary_bits: list[str] = []
            if env.temperature is not None:
                summary_bits.append(f"temp {env.temperature:.1f}C")
            if env.humidity is not None:
                summary_bits.append(f"hum {env.humidity:.0f}%")
            if env.pressure is not None:
                summary_bits.append(f"pressure {env.pressure:.0f}hPa")
            if env.voc is not None:
                summary_bits.append(f"voc {env.voc:.0f}")
            if env.pm25 is not None:
                summary_bits.append(f"pm25 {env.pm25:.0f}")
            if env.light is not None:
                summary_bits.append(f"light {env.light:.0f}lx")
            if env.soil_moisture is not None:
                summary_bits.append(f"soil {env.soil_moisture:.0f}%")
            if summary_bits:
                summary_line = f"  sensors: {', '.join(summary_bits)}"
                if len(summary_line) > 140:
                    summary_line = summary_line[:139] + "…"
                parts.append(summary_line)

            if env.temperature is not None:
                temp_str = f"  温度: {env.temperature}度 ({env.thermal_comfort}){_t('temperature')}{self._stale_note(env, 'temperature', now)}"
                if (env.temperature > _world_model.TEMP_HIGH and self._is_suppressed(zone_id, "temp_high")) or (
                    env.temperature < _world_model.TEMP_LOW and self._is_suppressed(zone_id, "temp_low")
                ):
                    temp_str += " (対応中)"
                parts.append(temp_str)
            if env.humidity is not None:
                parts.append(f"  湿度: {env.humidity}%{_t('humidity')}{self._stale_note(env, 'humidity', now)}")
            if env.co2 is not None:
                co2_str = f"  CO2: {int(env.co2)}ppm{_t('co2')}{self._stale_note(env, 'co2', now)}"
                if env.is_stuffy and (
                    self._is_suppressed(zone_id, "co2_high") or self._is_suppressed(zone_id, "co2_critical")
                ):
                    co2_str += " (対応中)"
                elif env.is_stuffy:
                    co2_str += " (換気推奨)"
                parts.append(co2_str)

            # Motion event frequency (_world_model.EventCounter)
            if zone.occupancy.motion_event_count_5min > 0:
                parts.append(f"  動体検知: 直近5分で{zone.occupancy.motion_event_count_5min}回")

            # Presence state (_world_model.StateTracker)
            if zone.occupancy.presence_state is not None:
                dur_min = int(zone.occupancy.presence_duration_sec / 60)
                state_str = "在室検知中" if zone.occupancy.presence_state else "不在"
                parts.append(f"  在室センサー: {state_str} ({dur_min}分間)")

            # Door states (_world_model.StateTracker)
            for dev_id, door_info in zone.occupancy.door_states.items():
                dur_min = int(door_info["duration_sec"] / 60)
                state_str = "開放中" if door_info["open"] else "閉鎖中"
                changes = door_info.get("changes_1h", 0)
                door_line = f"  ドア({dev_id}): {state_str} ({dur_min}分間)"
                if changes > 0:
                    door_line += f" [1h内 {changes}回開閉]"
                parts.append(door_line)

            if zone.occupancy and zone.occupancy.count > 0:
                parts.append(f"  在室: {zone.occupancy.count}人")
                if zone.occupancy.activity_class != "unknown":
                    parts.append(f"  活動: {zone.occupancy.activity_class} (レベル{zone.occupancy.activity_level:.1f})")
                if zone.occupancy.posture != "unknown":
                    duration_min = int(zone.occupancy.posture_duration_sec / 60)
                    parts.append(f"  姿勢: {zone.occupancy.posture} ({duration_min}分)")

            # VLM scene data — 3-stage freshness gate (independent of live occupancy)
            #   fresh (<300s)   → full description + objects + anomalies
            #   aged  (<1800s)  → prefix with "約N分前の観測" so LLM knows staleness
            #   stale (≥1800s)  → only keep minimal summary, and only if zone is occupied
            if zone.occupancy.vlm_last_update > 0:
                age_sec = _world_model.time.time() - zone.occupancy.vlm_last_update
                age_min = int(age_sec / 60)
                occ_now = zone.occupancy.count > 0 or zone.occupancy.inferred_occupied

                if age_sec < 300:
                    if zone.occupancy.scene_description:
                        parts.append(f"  シーン: {zone.occupancy.scene_description[:100]}")
                    if zone.occupancy.scene_objects:
                        objs = zone.occupancy.scene_objects[:6]
                        parts.append(f"  物体: [{', '.join(objs)}]")
                    if zone.occupancy.scene_anomalies:
                        parts.append(f"  異常検知: {', '.join(zone.occupancy.scene_anomalies[:3])}")
                elif age_sec < 1800:
                    if zone.occupancy.scene_description:
                        parts.append(f"  シーン (約{age_min}分前の観測): {zone.occupancy.scene_description[:100]}")
                    if zone.occupancy.scene_objects:
                        objs = zone.occupancy.scene_objects[:6]
                        parts.append(f"  物体 (約{age_min}分前): [{', '.join(objs)}]")
                    if zone.occupancy.scene_anomalies:
                        parts.append(f"  異常検知 (約{age_min}分前): {', '.join(zone.occupancy.scene_anomalies[:3])}")
                elif occ_now:
                    # Stale but zone still occupied — keep a terse summary only
                    obj_hint = (
                        f" 物体=[{', '.join(zone.occupancy.scene_objects[:4])}]" if zone.occupancy.scene_objects else ""
                    )
                    parts.append(f"  VLM最終観測: {age_min}分前{obj_hint}")

            # VLM history one-line summary: union of objects across last 3 snapshots
            # so the LLM has temporal context (e.g., dish appearing then disappearing).
            history = list(zone.occupancy.vlm_history)[-3:] if hasattr(zone.occupancy, "vlm_history") else []
            if len(history) >= 2:
                obj_union: list[str] = []
                for snap in history:
                    for o in (snap.objects or [])[:6]:
                        if o not in obj_union:
                            obj_union.append(o)
                latest = history[-1]
                hist_age_min = int((_world_model.time.time() - history[0].timestamp) / 60)
                obj_str = f"[{', '.join(obj_union[:8])}]" if obj_union else ""
                parts.append(
                    f"  VLM履歴 (過去{hist_age_min}分, {len(history)}観測): "
                    f"{obj_str} 最新「{(latest.description or '')[:60]}」"
                )

            lines.append("\n".join(parts))

        # Home devices (HA integration)
        hd = self.home_devices
        if hd.bridge_connected:
            home_parts = ["### スマートホーム"]
            lights_on = [lt for lt in hd.lights.values() if lt.on]
            lights_off = [lt for lt in hd.lights.values() if not lt.on]
            if lights_on:
                for lt in lights_on:
                    name = lt.entity_id.split(".")[-1] if "." in lt.entity_id else lt.entity_id
                    pct = int(lt.brightness / 255 * 100) if lt.brightness else 100
                    home_parts.append(f"  照明: {name} ON({pct}%)")
            if lights_off:
                names = ", ".join(
                    lt.entity_id.split(".")[-1] if "." in lt.entity_id else lt.entity_id for lt in lights_off
                )
                home_parts.append(f"  照明: {names} OFF")

            for c in hd.climates.values():
                name = c.entity_id.split(".")[-1] if "." in c.entity_id else c.entity_id
                mode_names = {
                    "off": "停止",
                    "cool": "冷房",
                    "heat": "暖房",
                    "dry": "除湿",
                    "fan_only": "送風",
                    "auto": "自動",
                }
                mode_ja = mode_names.get(c.mode, c.mode)
                temp_str = f"{c.target_temp:.0f}°C" if c.target_temp else ""
                curr_str = f" (室温{c.current_temp:.1f}°C)" if c.current_temp else ""
                home_parts.append(f"  エアコン: {name} {mode_ja}{temp_str}{curr_str}")

            for cv in hd.covers.values():
                name = cv.entity_id.split(".")[-1] if "." in cv.entity_id else cv.entity_id
                status = "全開" if cv.position >= 95 else "閉" if cv.position <= 5 else f"{cv.position}%"
                home_parts.append(f"  カーテン: {name} {status}")

            if hd.switches:
                on_switches = [k.split(".")[-1] if "." in k else k for k, v in hd.switches.items() if v]
                off_switches = [k.split(".")[-1] if "." in k else k for k, v in hd.switches.items() if not v]
                if on_switches:
                    home_parts.append(f"  スイッチ: {', '.join(on_switches)} ON")
                if off_switches:
                    home_parts.append(f"  スイッチ: {', '.join(off_switches)} OFF")

            # Binary sensors
            _DEVICE_CLASS_JA = {
                "door": "ドア",
                "window": "窓",
                "moisture": "水漏れ",
                "vibration": "振動",
                "motion": "モーション",
                "occupancy": "在室",
            }
            for bs in hd.binary_sensors.values():
                if bs.device_class == "moisture":
                    name = bs.entity_id.split(".")[-1] if "." in bs.entity_id else bs.entity_id
                    status = "検知" if bs.state else "正常"
                    prefix = "⚠ " if bs.state else ""
                    dc_ja = _DEVICE_CLASS_JA.get(bs.device_class, bs.device_class)
                    home_parts.append(f"  {prefix}{dc_ja}: {name} {status}")
                elif bs.state:
                    name = bs.entity_id.split(".")[-1] if "." in bs.entity_id else bs.entity_id
                    dc_ja = _DEVICE_CLASS_JA.get(bs.device_class, bs.device_class)
                    home_parts.append(f"  {dc_ja}: {name} 検知中")

            # HA sensors (power, air quality)
            for s in hd.sensors.values():
                name = s.entity_id.split(".")[-1] if "." in s.entity_id else s.entity_id
                if s.device_class == "power" and s.value > 0:
                    home_parts.append(f"  電力: {name} {s.value:.0f}{s.unit or 'W'}")
                elif s.device_class in ("carbon_dioxide", "pm25", "voc"):
                    dc_labels = {"carbon_dioxide": "CO2", "pm25": "PM2.5", "voc": "VOC"}
                    label = dc_labels.get(s.device_class, s.device_class)
                    home_parts.append(f"  {label}: {name} {s.value:.0f}{s.unit or ''}")

            if not hd.bridge_connected:
                home_parts.append("  ⚠ HAブリッジ: 切断中")
            lines.append("\n".join(home_parts))

        # Weather (weather-bridge)
        w = self.weather
        if w.last_update > 0 or w.alerts:
            weather_parts = ["### 天気"]
            if w.last_update > 0:
                weather_parts.append(
                    f"  現在: {w.condition} {w.temperature:.0f}°C 湿度{w.humidity:.0f}% 風速{w.wind_speed:.1f}m/s"
                )
            if w.alerts:
                _SEV_JA = {
                    "extreme": "最大",
                    "severe": "重大",
                    "moderate": "中程度",
                    "minor": "軽微",
                    "unknown": "",
                }
                for a in w.alerts[:5]:
                    sev = _SEV_JA.get(a.severity, a.severity)
                    prefix = "⚠ " if a.severity in ("extreme", "severe") else ""
                    title = a.title or "天気警報"
                    label = f"{prefix}警報[{sev}]" if sev else f"{prefix}警報"
                    suffix = f" ({a.area})" if a.area else ""
                    line = f"  {label}: {title}{suffix}"
                    if len(line) > 140:
                        line = line[:139] + "…"
                    weather_parts.append(line)
            lines.append("\n".join(weather_parts))

        return "\n\n".join(lines)

    def _get_digital_context(self) -> str:
        """Build digital space context (PC, services, GAS, knowledge)."""
        lines = []

        # PC state
        pc = self.pc_state
        if pc.cpu.last_update > 0 or pc.memory.last_update > 0:
            pc_parts = ["### PC"]
            if pc.cpu.last_update > 0:
                pc_parts.append(f"  CPU: {pc.cpu.usage_percent:.0f}% ({pc.cpu.core_count}コア)")
                if pc.cpu.temp_c > 0:
                    pc_parts.append(f"  CPU温度: {pc.cpu.temp_c:.0f}°C")
                if pc.cpu.usage_percent >= 80 and pc.top_processes:
                    top_cpu = sorted(pc.top_processes, key=lambda p: p.cpu_percent, reverse=True)[:3]
                    pc_parts.append(
                        "  上位プロセス(CPU): " + ", ".join(f"{p.name}({p.cpu_percent:.0f}%)" for p in top_cpu)
                    )
            if pc.memory.last_update > 0:
                pc_parts.append(
                    f"  メモリ: {pc.memory.used_gb:.1f}/{pc.memory.total_gb:.1f}GB ({pc.memory.percent:.0f}%)"
                )
                if pc.memory.percent >= 85 and pc.top_processes:
                    top_mem = sorted(pc.top_processes, key=lambda p: p.mem_mb, reverse=True)[:3]
                    pc_parts.append(
                        "  上位プロセス(メモリ): " + ", ".join(f"{p.name}({p.mem_mb / 1024:.1f}GB)" for p in top_mem)
                    )
            if pc.gpu.last_update > 0:
                pc_parts.append(
                    f"  GPU: {pc.gpu.usage_percent:.0f}%, VRAM {pc.gpu.vram_used_gb:.1f}/{pc.gpu.vram_total_gb:.1f}GB"
                )
                if pc.gpu.temp_c > 0:
                    pc_parts.append(f"  GPU温度: {pc.gpu.temp_c:.0f}°C")
            if pc.disk.partitions:
                for p in pc.disk.partitions:
                    pc_parts.append(f"  ディスク({p.mount}): {p.used_gb:.0f}/{p.total_gb:.0f}GB ({p.percent:.0f}%)")
            if not pc.bridge_connected:
                pc_parts.append("  ⚠ OpenClawブリッジ: 切断中")
            lines.append("\n".join(pc_parts))

        # Services state
        if self.services_state.services:
            svc_parts = ["### サービス"]
            for name, svc in self.services_state.services.items():
                if svc.error:
                    svc_parts.append(f"  {name}: ⚠ {svc.summary}")
                else:
                    svc_parts.append(f"  {name}: {svc.summary}")
            lines.append("\n".join(svc_parts))

        # GAS state
        gs = self.gas_state
        if gs.bridge_connected:
            gas_parts = ["### Google連携"]
            now_ts = _world_model.time.time()
            upcoming = [e for e in gs.calendar_events if e.start_ts > now_ts][:3]
            if upcoming:
                gas_parts.append("  予定:")
                for ev in upcoming:
                    time_str = ev.start.split("T")[1][:5] if "T" in ev.start else ev.start
                    gas_parts.append(f"    - {time_str} {ev.title}")
            else:
                gas_parts.append("  予定: なし")

            overdue = [t for t in gs.tasks if t.is_overdue]
            pending = [t for t in gs.tasks if t.status != "completed"]
            if overdue:
                gas_parts.append(f"  タスク: {len(pending)}件（期限切れ{len(overdue)}件）")
            elif pending:
                gas_parts.append(f"  タスク: {len(pending)}件")

            inbox = gs.gmail_labels.get("INBOX")
            if inbox and inbox.unread > 0:
                gas_parts.append(f"  Gmail未読: {inbox.unread}通")

            # Recent gmail subject/sender (VIP first, max 5, subject 60-char truncate)
            if gs.gmail_recent:

                def _is_vip(thread):
                    sender = str(thread.get("from", "") or thread.get("sender", "")).lower()
                    return any(v and v in sender for v in _world_model._VIP_GMAIL_SENDERS)

                vip = [t for t in gs.gmail_recent if _is_vip(t)]
                rest = [t for t in gs.gmail_recent if not _is_vip(t)]
                ordered = (vip + rest)[:5]
                if ordered:
                    gas_parts.append("  最近のGmail:")
                    for t in ordered:
                        subj = _world_model._sanitize_text(str(t.get("subject", "") or "(件名なし)"), 60)
                        sender = _world_model._sanitize_text(str(t.get("from", "") or t.get("sender", "")), 40)
                        vip_tag = "★ " if _is_vip(t) else ""
                        gas_parts.append(f"    - {vip_tag}{sender}: {subj}")

            # Free slots: show top 3 as HH:MM-HH:MM ranges (≥60 min); fall back to count for short slots
            long_slots = [s for s in gs.free_slots if s.duration_minutes >= 60]
            if long_slots:
                from datetime import datetime as _dt

                def _fmt_slot(s):
                    try:
                        start_t = _dt.fromisoformat(s.start.replace("Z", "+00:00")).strftime("%H:%M")
                        end_t = _dt.fromisoformat(s.end.replace("Z", "+00:00")).strftime("%H:%M")
                        return f"{start_t}-{end_t}"
                    except (ValueError, AttributeError):
                        return None

                slot_strs = [r for r in (_fmt_slot(s) for s in long_slots[:3]) if r]
                if slot_strs:
                    extra = f" (+{len(long_slots) - len(slot_strs)})" if len(long_slots) > len(slot_strs) else ""
                    gas_parts.append(f"  空き時間: {', '.join(slot_strs)}{extra}")
                else:
                    gas_parts.append(f"  空き時間(1h+): {len(long_slots)}スロット")

            lines.append("\n".join(gas_parts))

        # Knowledge base
        ks = self.knowledge_state
        if ks.bridge_connected:
            kb_parts = ["### ナレッジベース"]
            kb_parts.append(f"  ノート数: {ks.total_notes}")
            if ks.recent_changes:
                # Show up to 3 most recent changes so LLM can mention/build on what user was just working on
                latest = ks.recent_changes[-3:]
                titles = ", ".join(c.get("title", "") for c in latest if c.get("title"))
                if titles:
                    kb_parts.append(f"  直近の変更: {titles}")
            lines.append("\n".join(kb_parts))

        # External knowledge sources
        if ks.external_bridge_connected:
            ek_parts = ["### 外部ナレッジ"]
            ek_parts.append(f"  総ドキュメント数: {ks.external_total_docs}")
            for src in ks.external_sources:
                ek_parts.append(f"  ソース({src.name}): {src.doc_count}件")
            # Include up to 2 most recent knowledge_changed events with timing.
            recent_kn_events = [e for e in ks.events if e.event_type == "knowledge_changed"][-2:]
            if recent_kn_events:
                from datetime import datetime as _dt

                for e in recent_kn_events:
                    ts_str = _dt.fromtimestamp(e.timestamp).strftime("%H:%M") if e.timestamp else ""
                    ek_parts.append(f"  最近の更新 ({ts_str}): {e.description}")
            lines.append("\n".join(ek_parts))

        # News state
        ns = self.news_state
        if ns.bridge_connected or ns.daily_timestamp > 0:
            news_parts = ["### ニュース"]
            if ns.daily_timestamp > 0:
                from datetime import datetime as _dt

                ts_str = _dt.fromtimestamp(ns.daily_timestamp).strftime("%H:%M")
                news_parts.append(f"  最終サマリ: {ts_str} ({len(ns.daily_chunks)}カテゴリ)")
            if ns.urgent_articles:
                recent = [a for a in ns.urgent_articles if _world_model.time.time() - a.get("timestamp", 0) < 3600]
                if recent:
                    news_parts.append(f"  速報: {len(recent)}件 (直近1時間)")
            if not ns.bridge_connected:
                news_parts.append("  ⚠ ニュースブリッジ: 切断中")
            lines.append("\n".join(news_parts))

        return "\n\n".join(lines)

    def _get_user_context(self) -> str:
        """Build user state context (occupancy summary + biometrics + schedule)."""
        lines = []

        # Occupancy summary — include both camera-confirmed and inferred occupancy
        # so the LLM sees why the system thinks someone is (or isn't) home.
        occupied_zones = {
            zid: z
            for zid, z in self.zones.items()
            if z.occupancy and (z.occupancy.count > 0 or z.occupancy.inferred_occupied)
        }
        if occupied_zones:
            occ_parts = ["### 在室状態"]
            for zid, z in occupied_zones.items():
                occ = z.occupancy
                if occ.count > 0:
                    status = f"  {zid}: {occ.count}人 (カメラ確認)"
                else:
                    srcs = ", ".join(occ.inference_sources) if occ.inference_sources else "?"
                    status = f"  {zid}: 在室推定 (根拠: {srcs})"
                if occ.activity_class != "unknown":
                    status += f", 活動={occ.activity_class} ({occ.activity_level:.2f})"
                if occ.posture != "unknown":
                    dur = int(occ.posture_duration_sec / 60)
                    # Highlight sustained seated/lying posture as a streak to make
                    # sedentary judgement explicit material for the LLM
                    if occ.posture in ("sitting", "lying") and dur >= 30:
                        status += f", 姿勢={occ.posture} ({dur}分streak)"
                    else:
                        status += f", 姿勢={occ.posture}({dur}分)"
                occ_parts.append(status)
            lines.append("\n".join(occ_parts))
        elif self.zones:
            # All zones empty — make "unoccupied" explicit and list the sources
            # the system checked, so the LLM doesn't silently assume the user
            # is home on stale data.
            lines.append("### 在室状態\n  全ゾーン不在 (カメラ/PIR/PC/生体いずれも反応なし)")

        # Schedule predictions (arrival/wake)
        sched = self.user.schedule
        if sched.last_update > 0 and (sched.next_arrival_ts or sched.next_wake_ts or sched.weekday_arrival_str):
            from datetime import datetime as _dt

            sc_parts = ["### 生活パターン"]
            now_ts = _world_model.time.time()
            if sched.next_arrival_ts > now_ts:
                mins = int((sched.next_arrival_ts - now_ts) / 60)
                ts_str = _dt.fromtimestamp(sched.next_arrival_ts).strftime("%H:%M")
                sc_parts.append(f"  帰宅予測: {ts_str} (あと{mins}分)")
            if sched.next_wake_ts > now_ts:
                mins = int((sched.next_wake_ts - now_ts) / 60)
                ts_str = _dt.fromtimestamp(sched.next_wake_ts).strftime("%m/%d %H:%M")
                sc_parts.append(f"  次回起床予測: {ts_str} (あと{mins}分)")
            if sched.weekday_arrival_str:
                stdev_str = f" (±{sched.arrival_stdev_min}分)" if sched.arrival_stdev_min else ""
                sc_parts.append(f"  今日の曜日の帰宅傾向: {sched.weekday_arrival_str}{stdev_str}")
            if sched.weekday_wake_str:
                sc_parts.append(f"  今日の曜日の起床傾向: {sched.weekday_wake_str}")
            if len(sc_parts) > 1:
                lines.append("\n".join(sc_parts))

        # Biometrics
        bio = self.biometric_state
        if bio.last_update > 0:
            now_ts = _world_model.time.time()

            def _stale_tag(last: float) -> str:
                """Stage label for biometric data freshness.

                <10min: live / <60min: N分前 / >=60min: stale
                LLM uses this to weigh whether the value should drive a decision.
                """
                if not last or last <= 0:
                    return ""
                age = now_ts - last
                if age < 600:
                    return " (live)"
                if age < 3600:
                    return f" ({int(age / 60)}分前)"
                if age < 86400:
                    return f" (stale: {int(age / 3600)}時間前)"
                return f" (stale: {int(age / 86400)}日前)"

            bio_parts = ["### バイオメトリクス"]
            if bio.heart_rate.bpm is not None:
                hr_str = (
                    f"  心拍: {bio.heart_rate.bpm}bpm ({bio.heart_rate.zone}){_stale_tag(bio.heart_rate.last_update)}"
                )
                if bio.heart_rate.resting_bpm is not None:
                    hr_str += f", 安静時{bio.heart_rate.resting_bpm}bpm"
                bio_parts.append(hr_str)
            if bio.spo2.percent is not None:
                bio_parts.append(f"  SpO2: {bio.spo2.percent}%{_stale_tag(bio.spo2.last_update)}")
            if bio.stress.last_update > 0:
                bio_parts.append(
                    f"  ストレス: {bio.stress.category} ({bio.stress.level}){_stale_tag(bio.stress.last_update)}"
                )
            if bio.fatigue.last_update > 0:
                bio_parts.append(f"  疲労度: {bio.fatigue.score}/100{_stale_tag(bio.fatigue.last_update)}")
            if bio.sleep.last_update > 0:
                sleep_str = f"  睡眠: {bio.sleep.duration_minutes}分"
                if bio.sleep.quality_score > 0:
                    sleep_str += f" (品質{bio.sleep.quality_score}/100)"
                if bio.sleep.stage != "unknown":
                    sleep_str += f", ステージ={bio.sleep.stage}"
                sleep_str += _stale_tag(bio.sleep.last_update)
                bio_parts.append(sleep_str)
            if bio.hrv.rmssd_ms is not None:
                bio_parts.append(f"  HRV(RMSSD): {bio.hrv.rmssd_ms}ms{_stale_tag(bio.hrv.last_update)}")
            if bio.body_temperature.celsius is not None:
                bio_parts.append(
                    f"  体温: {bio.body_temperature.celsius:.1f}°C{_stale_tag(bio.body_temperature.last_update)}"
                )
            if bio.respiratory_rate.breaths_per_minute is not None:
                bio_parts.append(
                    f"  呼吸数: {bio.respiratory_rate.breaths_per_minute}回/分"
                    f"{_stale_tag(bio.respiratory_rate.last_update)}"
                )
            if bio.activity.last_update > 0:
                pct = int(bio.activity.goal_progress * 100)
                bio_parts.append(
                    f"  歩数: {bio.activity.steps}/{bio.activity.steps_goal} ({pct}%)"
                    f"{_stale_tag(bio.activity.last_update)}"
                )
            if not bio.bridge_connected:
                bio_parts.append("  ⚠ バイオメトリクスブリッジ: 切断中")
            lines.append("\n".join(bio_parts))

        # Screen time
        st = self.user.screen_time
        if st.total_minutes > 0:
            hours = st.total_minutes // 60
            mins = st.total_minutes % 60
            lines.append(f"### スクリーンタイム\n  今日: {hours}h{mins}m")

        return "\n\n".join(lines)
