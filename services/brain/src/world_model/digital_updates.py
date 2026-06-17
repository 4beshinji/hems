"""WorldModel mixin extracted from the facade module."""

import time

from loguru import logger

from .data_classes import (
    CalendarEvent,
    CPUData,
    DiskData,
    DiskPartition,
    DriveFile,
    Event,
    FreeSlot,
    GmailLabel,
    GoogleTask,
    GPUData,
    MemoryData,
    ProcessInfo,
    ServiceStatusData,
    SheetData,
    ShoppingItemData,
)
from .sanitizer import _sanitize_text
from .vip_detector import _detect_service_vip


class DigitalUpdatesMixin:
    def _update_pc_state(self, path_parts: list[str], payload: dict):
        """Handle hems/pc/* topics from OpenClaw bridge."""
        if not path_parts:
            return

        category = path_parts[0]
        pc = self.pc_state

        if category == "metrics" and len(path_parts) >= 2:
            metric = path_parts[1]
            now = time.time()
            if metric == "cpu":
                prev_usage = pc.cpu.usage_percent
                pc.cpu = CPUData(
                    usage_percent=payload.get("usage_percent", 0),
                    core_count=payload.get("core_count", 0),
                    freq_mhz=payload.get("freq_mhz", 0),
                    temp_c=payload.get("temp_c", 0),
                    last_update=now,
                )
                self._check_pc_thresholds("cpu", pc.cpu.usage_percent, prev_usage)
            elif metric == "memory":
                prev_pct = pc.memory.percent
                pc.memory = MemoryData(
                    used_gb=payload.get("used_gb", 0),
                    total_gb=payload.get("total_gb", 0),
                    percent=payload.get("percent", 0),
                    last_update=now,
                )
                self._check_pc_thresholds("memory", pc.memory.percent, prev_pct)
            elif metric == "gpu":
                prev_temp = pc.gpu.temp_c
                pc.gpu = GPUData(
                    usage_percent=payload.get("usage_percent", 0),
                    vram_used_gb=payload.get("vram_used_gb", 0),
                    vram_total_gb=payload.get("vram_total_gb", 0),
                    temp_c=payload.get("temp_c", 0),
                    last_update=now,
                )
                self._check_pc_thresholds("gpu_temp", pc.gpu.temp_c, prev_temp)
            elif metric == "disk":
                partitions = [
                    DiskPartition(
                        mount=p.get("mount", ""),
                        used_gb=p.get("used_gb", 0),
                        total_gb=p.get("total_gb", 0),
                        percent=p.get("percent", 0),
                    )
                    for p in payload.get("partitions", [])
                ]
                pc.disk = DiskData(partitions=partitions, last_update=now)
                for p in partitions:
                    if p.percent > self.thresholds.pc_disk_high:
                        pc.add_event(
                            Event(
                                event_type="pc_disk_high",
                                description=f"ディスク残量警告: {p.mount} ({p.percent:.0f}%使用)",
                                severity=1,
                                data={"mount": p.mount, "percent": p.percent},
                            )
                        )
            elif metric == "temperature":
                if "cpu_temp_c" in payload:
                    pc.cpu.temp_c = payload["cpu_temp_c"]
                if "gpu_temp_c" in payload:
                    pc.gpu.temp_c = payload["gpu_temp_c"]

        elif category == "processes" and len(path_parts) >= 2 and path_parts[1] == "top":
            pc.top_processes = [
                ProcessInfo(
                    pid=p.get("pid", 0),
                    name=p.get("name", ""),
                    cpu_percent=p.get("cpu_percent", 0),
                    mem_mb=p.get("mem_mb", 0),
                )
                for p in payload.get("processes", [])
            ]

        elif category == "bridge" and len(path_parts) >= 2 and path_parts[1] == "status":
            pc.bridge_connected = payload.get("connected", False)

        elif category == "events":
            # Threshold events from bridge (cpu_high, memory_high, gpu_hot, disk_low)
            event_type = path_parts[1] if len(path_parts) >= 2 else "unknown"
            pc.add_event(
                Event(
                    event_type=f"pc_{event_type}",
                    description=f"PC閾値イベント: {event_type}",
                    severity=1 if "hot" not in event_type else 2,
                    data=payload,
                )
            )

        # Update screen time tracking when PC metrics are received
        if pc.bridge_connected and pc.cpu.last_update > 0:
            self._update_screen_time(pc.cpu.last_update)

    def _update_screen_time(self, now: float):
        """Track daily screen time based on PC activity."""
        st = self.user.screen_time
        from datetime import datetime

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

        # Reset daily counter if new day
        if st.session_start_ts < today_start:
            st.total_minutes = 0
            st.session_start_ts = now
        elif st.last_update > 0:
            # Increment by elapsed time since last update (cap at 5 min gap)
            elapsed = now - st.last_update
            if 0 < elapsed < 300:
                st.total_minutes += int(elapsed / 60)
        else:
            st.session_start_ts = now

        st.last_update = now

    def _check_pc_thresholds(self, metric: str, value: float, prev: float):
        """Generate events from PC metric threshold crossings."""
        pc = self.pc_state
        if metric == "cpu" and value > self.thresholds.pc_cpu_high and prev <= self.thresholds.pc_cpu_high:
            pc.add_event(
                Event(
                    event_type="pc_cpu_high",
                    description=f"PC CPU使用率高: {value:.0f}%",
                    severity=1,
                    data={"usage_percent": value},
                )
            )
        elif metric == "memory" and value > self.thresholds.pc_memory_high and prev <= self.thresholds.pc_memory_high:
            pc.add_event(
                Event(
                    event_type="pc_memory_high",
                    description=f"PCメモリ使用率高: {value:.0f}%",
                    severity=1,
                    data={"percent": value},
                )
            )
        elif (
            metric == "gpu_temp"
            and value > self.thresholds.pc_gpu_temp_high
            and prev <= self.thresholds.pc_gpu_temp_high
        ):
            pc.add_event(
                Event(
                    event_type="pc_gpu_hot",
                    description=f"GPU温度警告: {value:.0f}°C",
                    severity=2,
                    data={"temp_c": value},
                )
            )

    def _update_service_state(self, service_name: str, msg_type: str, payload: dict):
        """Handle hems/services/{name}/status and hems/services/{name}/event topics."""
        ss = self.services_state

        if msg_type == "status":
            prev = ss.services.get(service_name)
            prev_count = prev.unread_count if prev else 0

            ssd = ServiceStatusData(
                name=_sanitize_text(payload.get("name", service_name), 50),
                available=bool(payload.get("available", True)),
                unread_count=int(payload.get("unread_count", 0)),
                summary=_sanitize_text(payload.get("summary", "")),
                details=payload.get("details", {}),
                last_check=payload.get("last_check", time.time()),
                error=_sanitize_text(payload.get("error", "") or "", 100) or None,
            )
            ss.services[service_name] = ssd

            # Generate event on unread increase
            if ssd.unread_count > prev_count:
                ss.add_event(
                    Event(
                        event_type="service_unread_increase",
                        description=ssd.summary,
                        severity=0,
                        data={"service": service_name, "prev": prev_count, "new": ssd.unread_count},
                    )
                )

        elif msg_type == "event":
            is_vip = _detect_service_vip(service_name, payload)
            event_type = "service_vip_event" if is_vip else f"service_{payload.get('type', 'unknown')}"
            data_with_vip = dict(payload)
            data_with_vip["service"] = service_name
            data_with_vip["vip"] = is_vip
            ss.add_event(
                Event(
                    event_type=event_type,
                    description=_sanitize_text(payload.get("summary", f"{service_name} event")),
                    severity=2 if is_vip else 0,
                    data=data_with_vip,
                )
            )

    def _update_gas_state(self, path_parts: list[str], payload: dict):
        """Handle hems/gas/* topics from GAS bridge."""
        if not path_parts:
            return

        gs = self.gas_state
        category = path_parts[0]

        if category == "calendar" and len(path_parts) >= 2:
            sub = path_parts[1]
            if sub == "upcoming":
                events = []
                for ev in payload.get("events", []):
                    start_ts = self._parse_iso_ts(ev.get("start", ""))
                    end_ts = self._parse_iso_ts(ev.get("end", ""))
                    events.append(
                        CalendarEvent(
                            id=ev.get("id", ""),
                            title=ev.get("title", ""),
                            start=ev.get("start", ""),
                            end=ev.get("end", ""),
                            location=ev.get("location", ""),
                            calendar_name=ev.get("calendarName", ""),
                            is_all_day=ev.get("isAllDay", False),
                            description=ev.get("description", ""),
                            start_ts=start_ts,
                            end_ts=end_ts,
                        )
                    )
                gs.calendar_events = events
                gs.last_calendar_update = time.time()
                gs.bridge_connected = True

            elif sub == "free_slots":
                gs.free_slots = [
                    FreeSlot(
                        start=s.get("start", ""),
                        end=s.get("end", ""),
                        duration_minutes=s.get("duration_minutes", 0),
                    )
                    for s in payload.get("slots", [])
                ]

        elif category == "tasks" and len(path_parts) >= 2:
            sub = path_parts[1]
            tasks = []
            for tl in payload.get("taskLists", []):
                list_name = tl.get("title", "")
                for t in tl.get("tasks", []):
                    tasks.append(
                        GoogleTask(
                            id=t.get("id", ""),
                            title=t.get("title", ""),
                            notes=t.get("notes", ""),
                            due=t.get("due", ""),
                            status=t.get("status", ""),
                            list_name=list_name,
                            is_overdue=t.get("is_overdue", False),
                        )
                    )
            if sub == "all":
                gs.tasks = tasks
                gs.last_tasks_update = time.time()
            elif sub == "due_today":
                # Overwrite tasks list with due_today data (richer with is_overdue)
                gs.tasks = tasks
                gs.last_tasks_update = time.time()
            gs.bridge_connected = True

        elif category == "gmail" and len(path_parts) >= 2:
            sub = path_parts[1]
            if sub == "summary":
                gs.gmail_labels = {}
                for name, data in payload.get("labels", {}).items():
                    gs.gmail_labels[name] = GmailLabel(
                        name=name,
                        unread=data.get("unread", 0),
                        total=data.get("total", 0) or 0,
                    )
                gs.last_gmail_update = time.time()
                gs.bridge_connected = True
            elif sub == "recent":
                gs.gmail_recent = payload.get("threads", [])

        elif category == "sheets" and len(path_parts) >= 2:
            sheet_name = path_parts[1]
            gs.sheets[sheet_name] = SheetData(
                name=sheet_name,
                values=payload.get("values", []),
                headers=payload.get("headers", []),
                last_update=time.time(),
            )
            gs.bridge_connected = True

        elif category == "drive" and len(path_parts) >= 2:
            sub = path_parts[1]
            if sub == "recent":
                gs.drive_recent = [
                    DriveFile(
                        name=f.get("name", ""),
                        mime_type=f.get("mimeType", ""),
                        modified_time=f.get("modifiedTime", ""),
                        url=f.get("url", ""),
                    )
                    for f in payload.get("files", [])
                ]
                gs.bridge_connected = True

        elif category == "bridge" and len(path_parts) >= 2:
            if path_parts[1] == "status":
                gs.bridge_connected = payload.get("connected", False)

    @staticmethod
    def _parse_iso_ts(iso_str: str) -> float:
        """Parse ISO 8601 string to UNIX timestamp. Returns 0 on failure."""
        if not iso_str:
            return 0
        try:
            from datetime import datetime

            # Handle Z suffix and various formats
            s = iso_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt.timestamp()
        except (ValueError, TypeError):
            return 0

    def _update_vlm(self, path_parts: list[str], payload: dict):
        """Handle hems/perception/* topics (VLM scene analysis + model swap)."""
        if not path_parts:
            return

        # hems/perception/vlm/{zone} — scene analysis result
        if (
            len(path_parts) >= 2
            and path_parts[0] == "vlm"
            and path_parts[1] != "model_swap"
            and path_parts[1] != "status"
        ):
            zone_id = path_parts[1]
            zone = self._get_zone(zone_id)
            now = time.time()

            description = _sanitize_text(payload.get("description", ""), 500)
            objects = payload.get("objects", [])
            scene_type = payload.get("scene_type", "unknown")
            anomalies = payload.get("anomalies", [])

            # Sanitize list items
            if isinstance(objects, list):
                objects = [_sanitize_text(str(o), 50) for o in objects[:20]]
            else:
                objects = []
            if isinstance(anomalies, list):
                anomalies = [_sanitize_text(str(a), 50) for a in anomalies[:10]]
            else:
                anomalies = []

            scene_type_clean = _sanitize_text(str(scene_type), 30)
            prev_anomalies = zone.occupancy.scene_anomalies
            zone.occupancy.scene_description = description
            zone.occupancy.scene_objects = objects
            zone.occupancy.scene_type = scene_type_clean
            zone.occupancy.scene_anomalies = anomalies
            zone.occupancy.vlm_last_update = now

            # Append to rolling history (maxlen 10, drop entries older than 1h)
            from .data_classes import SceneSnapshot

            snapshot = SceneSnapshot(
                timestamp=now,
                description=description,
                objects=list(objects),
                scene_type=scene_type_clean,
                anomalies=list(anomalies),
                tier=_sanitize_text(str(payload.get("tier", "")), 10),
                model=_sanitize_text(str(payload.get("model", "")), 40),
            )
            hist = zone.occupancy.vlm_history
            hist.append(snapshot)
            cutoff = now - 3600
            zone.occupancy.vlm_history = [s for s in hist if s.timestamp >= cutoff][-10:]

            # Anomaly tracking state for re-evaluation rule
            if anomalies:
                if not prev_anomalies or set(anomalies) != set(prev_anomalies):
                    # New or changed anomaly set → reset tracker
                    zone.occupancy.anomaly_first_seen = now
                    zone.occupancy.anomaly_escalated = False
                    zone.occupancy.anomaly_rescan_requested = 0
            else:
                # Anomaly cleared
                zone.occupancy.anomaly_first_seen = 0
                zone.occupancy.anomaly_escalated = False
                zone.occupancy.anomaly_rescan_requested = 0

            # Generate events for anomalies
            if anomalies:
                zone.add_event(
                    Event(
                        event_type="vlm_anomaly",
                        description=f"VLM検知: {', '.join(anomalies[:3])}",
                        severity=1,
                        zone=zone_id,
                        data={
                            "anomalies": anomalies,
                            "description": description[:200],
                            "model": payload.get("model", ""),
                            "tier": payload.get("tier", ""),
                        },
                    )
                )

        # hems/perception/vlm/model_swap — VRAM coordination
        elif len(path_parts) >= 2 and path_parts[0] == "vlm" and path_parts[1] == "model_swap":
            status = payload.get("status", "")
            stats = self.vlm_swap_stats
            now_ts = time.time()
            if status == "heavy_loading":
                self.vlm_model_swap_active = True
                stats["last_swap_start_ts"] = now_ts
                logger.info("VLM model swap: heavy model loading — brain entering rule-only mode")
            elif status == "ready":
                self.vlm_model_swap_active = False
                start = stats.get("last_swap_start_ts", 0)
                if start > 0:
                    duration = now_ts - start
                    stats["last_swap_end_ts"] = now_ts
                    stats["last_swap_duration_sec"] = duration
                    if duration > stats.get("longest_swap_sec", 0):
                        stats["longest_swap_sec"] = duration
                stats["success_count"] = stats.get("success_count", 0) + 1
                logger.info("VLM model swap: ready — brain resuming LLM mode")
            elif status in ("failed", "error"):
                self.vlm_model_swap_active = False
                stats["failure_count"] = stats.get("failure_count", 0) + 1
                logger.warning(f"VLM model swap failed: {payload.get('error', '')}")

    def _update_knowledge_state(self, msg_type: str, payload: dict):
        """Handle hems/personal/notes/stats and hems/personal/notes/changed."""
        ks = self.knowledge_state

        if msg_type == "stats":
            ks.total_notes = payload.get("total_notes", 0)
            ks.indexed = payload.get("indexed", 0)
            ks.bridge_connected = True

        elif msg_type == "changed":
            ks.bridge_connected = True
            change = {
                "path": _sanitize_text(payload.get("path", ""), 150),
                "title": _sanitize_text(payload.get("title", ""), 100),
                "action": _sanitize_text(payload.get("action", ""), 30),
            }
            ks.add_recent_change(change)
            ks.add_event(
                Event(
                    event_type="note_changed",
                    description=f"ノート変更: {change['title']} ({change['action']})",
                    severity=0,
                    data=payload,
                )
            )

    def _update_external_knowledge_state(self, msg_type: str, payload: dict):
        """Handle hems/personal/knowledge/stats and hems/personal/knowledge/changed."""
        from world_model.data_classes import KnowledgeSourceInfo

        ks = self.knowledge_state

        if msg_type == "stats":
            ks.external_bridge_connected = True
            ks.external_total_docs = payload.get("total_docs", 0)
            sources = payload.get("sources", [])
            ks.external_sources = [
                KnowledgeSourceInfo(
                    name=s.get("name", ""),
                    doc_count=s.get("doc_count", 0),
                    type_counts=s.get("type_counts", {}),
                )
                for s in sources
            ]

        elif msg_type == "changed":
            ks.external_bridge_connected = True
            title = _sanitize_text(payload.get("title", ""), 100)
            source = _sanitize_text(payload.get("source", ""), 50)
            action = _sanitize_text(payload.get("action", ""), 30)
            ks.add_event(
                Event(
                    event_type="knowledge_changed",
                    description=f"外部ナレッジ変更: {source}/{title} ({action})",
                    severity=0,
                    data=payload,
                )
            )

    def _update_shopping_state(self, sub_topic: str, payload: dict):
        """Handle hems/shopping/list snapshot from backend.

        Backend publishes the full pending list on every mutation; we rebuild
        ShoppingState from it so the recurring-due / departure reminder rules
        (rules/shopping.py) read live data. The per-event topics
        (added/updated/purchased) are handled elsewhere (ShoppingClassifier).
        """
        if sub_topic != "list":
            return

        ss = self.shopping_state
        raw_items = payload.get("items", []) if isinstance(payload, dict) else []
        items: list[ShoppingItemData] = []
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            items.append(
                ShoppingItemData(
                    id=int(it.get("id", 0) or 0),
                    name=_sanitize_text(it.get("name", ""), 100),
                    category=_sanitize_text(it.get("category", ""), 50),
                    quantity=int(it.get("quantity", 1) or 1),
                    unit=_sanitize_text(it.get("unit", ""), 20),
                    store=_sanitize_text(it.get("store", ""), 50),
                    store_category=_sanitize_text(it.get("store_category", ""), 30),
                    price=int(it.get("price", 0) or 0),
                    is_recurring=bool(it.get("is_recurring", False)),
                    recurrence_days=int(it.get("recurrence_days", 0) or 0),
                    priority=int(it.get("priority", 1) or 1),
                    created_by=_sanitize_text(it.get("created_by", "user"), 30),
                    next_purchase_at=float(it.get("next_purchase_at", 0) or 0),
                )
            )
        ss.items = items
        ss.last_update = time.time()
