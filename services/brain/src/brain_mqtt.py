import asyncio
import json
import time
from datetime import datetime

from loguru import logger

from brain_constants import (
    BIOMETRIC_ENABLED,
    GAS_ENABLED,
    HA_ENABLED,
    NEWS_ENABLED,
    OBSIDIAN_ENABLED,
    OPENCLAW_ENABLED,
    SWITCHBOT_ENABLED,
    WAKE_DETECT_HOUR_END,
    WAKE_DETECT_HOUR_START,
)
from device_dispatcher import parse_mqtt as parse_device_mqtt
from device_dispatcher import parse_z2m_bridge_devices
from world_model.sensor_fusion import ChannelType, classify_channel
from world_model.sensor_validation import validate_sensor_value


class MqttSyncMixin:
    def on_connect(self, client, userdata, flags, rc, properties=None):
        logger.info(f"Connected to MQTT Broker (rc={rc})")
        client.subscribe("mcp/+/response/#")
        # W3.8c: sensor/camera/activity プレフィックスは hems/sensors/* に統一済。
        # office/* は task_report のみ残存（backend → brain）。
        client.subscribe("office/+/task_report/#")
        client.subscribe("hems/#")
        client.subscribe("zigbee2mqtt/#")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        if "mcp" in msg.topic and "response" in msg.topic:
            self.mcp.handle_response(msg.topic, payload)
            return

        if msg.topic == "hems/brain/reload-character":
            logger.info("Character reload command received")
            from character_loader import reload_character

            self.character = reload_character()
            if self.persona_rewriter:
                self.persona_rewriter.update_character(self.character)
            if self.ambient_speaker:
                self.ambient_speaker.character = self.character
            return

        if msg.topic == "hems/brain/guest-mode":
            enabled = payload.get("enabled", True)
            hours = payload.get("duration_hours", 3)
            self.world_model.set_guest_mode(enabled, hours)
            logger.info(f"Guest mode {'enabled' if enabled else 'disabled'} via MQTT (duration={hours}h)")
            return

        if msg.topic == "hems/brain/set-power-mode":
            mode = payload.get("mode", "normal")
            if mode in ("normal", "sleep", "away"):
                self.power_mode_manager.force_mode(mode, "手動設定（ダッシュボード）")
                logger.info("Power mode manually set to: %s", mode)
            return

        if msg.topic == "hems/brain/batch-run":
            tasks = payload.get("tasks", [])
            model = payload.get("model")
            if self._loop and tasks:
                asyncio.run_coroutine_threadsafe(self._run_batch(tasks, model), self._loop)
            return

        if self._loop:
            self._loop.call_soon_threadsafe(self._process_mqtt, msg.topic, payload)

    def _process_mqtt(self, topic: str, payload):
        # Thin orchestrator: each step is an extracted method. The recorded order
        # below IS the execution order and preserves the three mandatory ordering
        # invariants (see docs/refactor/2026-06-11/W2.6-design-note.md §2):
        #   (1) S0 enrich must run before S1 update_from_mqtt.
        #   (2) wake_up_fired aggregate → sunrise stop (stop stays here, not in S7).
        #   (3) _maybe_trigger_cycle must run last, after all world_model mutations.
        parts = topic.split("/")

        self._enrich_payload(topic, payload)  # S0 (must precede S1)
        self.world_model.update_from_mqtt(topic, payload)  # S1
        self._feed_shopping_classifier(topic, payload)  # S2
        self._trigger_timeline_on_event(topic, parts)  # S3
        self._mark_intervention(topic, parts)  # S4
        self._feed_schedule_learner_occupancy(topic, payload, parts)  # S5
        self._feed_schedule_learner_sleep(topic, payload)  # S6
        woke = self._detect_wake_up(topic, payload, parts)  # S7
        # Sunrise alarm: cancel ramp + turn off light on wake_up. Aggregated flag
        # from S7 is evaluated here so multi-path detection stops sunrise once.
        if woke and self.sunrise_alarm and self.sunrise_alarm.is_active:
            self.sunrise_alarm.stop(self.client)
        self._record_to_event_store(topic, payload, parts)  # S8
        self._update_device_registry(topic, payload, parts)  # S9a
        self._maybe_trigger_cycle()  # S9b (must be last)

    def _enrich_payload(self, topic: str, payload) -> None:
        """S0: enrich Z2M payloads with zone from Device Registry (in-place)."""
        if (
            isinstance(payload, dict)
            and topic.startswith("zigbee2mqtt/")
            and not topic.startswith("zigbee2mqtt/bridge")
        ):
            vendor_ref = topic.split("/", 1)[1]
            zone = self._device_zone_map.get(vendor_ref)
            if zone and "zone" not in payload:
                payload["zone"] = zone

    def _feed_shopping_classifier(self, topic: str, payload) -> None:
        """S2: feed shopping add/purchase events to the classifier coroutine."""
        if topic == "hems/shopping/added" and self.shopping_classifier and self._loop:
            asyncio.run_coroutine_threadsafe(self.shopping_classifier.handle_added_event(payload), self._loop)
        elif topic == "hems/shopping/purchased" and self.shopping_classifier and self._loop:
            asyncio.run_coroutine_threadsafe(self.shopping_classifier.handle_purchased_event(payload), self._loop)

    def _trigger_timeline_on_event(self, topic: str, parts: list[str]) -> None:
        """S3: trigger timeline regeneration on calendar / task lifecycle events."""
        if self.timeline_generator and self._loop:
            if topic == "hems/gas/calendar/upcoming":
                self._loop.call_soon_threadsafe(self._trigger_timeline_regen, "calendar_update")
            elif topic.startswith("hems/task/"):
                if len(parts) >= 3 and parts[2] in ("created", "dismissed", "completed", "locked"):
                    self._loop.call_soon_threadsafe(self._trigger_timeline_regen, f"task_{parts[2]}")

    def _mark_intervention(self, topic: str, parts: list[str]) -> None:
        """S4: mark a tracked task completed (intervention efficacy, Group D).

        Plain thread-safe append, so it runs regardless of timeline_generator.
        """
        if self.event_writer and topic.startswith("hems/task/completed/"):
            if len(parts) >= 4:
                self.event_writer.mark_intervention_completed(parts[3])

    def _feed_schedule_learner_occupancy(self, topic: str, payload, parts: list[str]) -> None:
        """S5: feed occupancy changes to schedule learner.

        We unify transitions across camera, PIR/presence binary sensors, and
        biometric HR so the learner gets arrivals/departures even when the
        camera is offline or the zone has no camera at all.
        """
        if not self.schedule_learner:
            return
        # None until a presence-bearing topic matches below, so reconcile_presence
        # only runs for occupancy-relevant messages rather than every MQTT message.
        inferred = None

        # Camera person count (hems/sensors/{zone}/camera/{cam}/status)
        if len(parts) >= 6 and parts[0] == "hems" and parts[1] == "sensors" and parts[3] == "camera":
            inferred = int(payload.get("person_count", payload.get("count", 0)))

        # HA/SwitchBot/Zigbee-via-HA binary_sensor presence/occupancy/motion
        elif len(parts) >= 6 and parts[0] == "hems" and parts[1] == "home" and parts[3] == "binary_sensor":
            dc = payload.get("device_class", "")
            if dc in ("motion", "occupancy", "presence"):
                raw = payload.get("state", "off")
                inferred = 1 if raw in ("on", "detected", "open") else 0

        # Biometric HR arrival: a fresh HR reading implies the user is home.
        # Only a 0→1 flip is meaningful; the learner debounces on its side.
        elif (
            len(parts) >= 4
            and parts[0] == "hems"
            and parts[1] == "personal"
            and parts[2] == "biometrics"
            and topic.endswith("/heart_rate")
            and payload.get("bpm")
        ):
            inferred = 1

        if inferred is not None:
            # Use reconciled presence as the authoritative signal so individual
            # sensor flaps don't generate spurious arrivals/departures.
            self.world_model.reconcile_presence()
            aggregated = 1 if self.world_model.is_anyone_home() else 0
            self.schedule_learner.update_occupancy(aggregated)

    def _feed_schedule_learner_sleep(self, topic: str, payload) -> None:
        """S6: feed biometric sleep data to schedule learner."""
        if self.schedule_learner and "biometrics" in topic and "/sleep" in topic:
            sleep_end = payload.get("sleep_end_ts", 0)
            sleep_start = payload.get("sleep_start_ts", 0)
            if sleep_end > 0:
                self.schedule_learner.record_sleep_from_biometrics(sleep_start, sleep_end)

    def _detect_wake_up(self, topic: str, payload, parts: list[str]) -> bool:
        """S7: wake-up detection for EventAutomation. Returns aggregated wake flag.

        Both the biometric sleep-end path and the morning-camera path are
        independent ``if`` branches (either may fire for a given message). The
        sunrise-alarm stop is intentionally NOT performed here: the caller
        aggregates the returned flag and stops sunrise once (design note §2-2).
        """
        wake_up_fired = False
        if self.event_automation:
            # Biometric sleep end → wake_up
            if "biometrics" in topic and "/sleep" in topic:
                sleep_end = payload.get("sleep_end_ts", 0)
                if sleep_end > 0:
                    wake_up_fired = True
                    if self._loop:
                        asyncio.run_coroutine_threadsafe(self.event_automation.trigger("wake_up"), self._loop)
                        if self.automation_engine:
                            asyncio.run_coroutine_threadsafe(
                                self.automation_engine.trigger_event("wake_up"), self._loop
                            )

            # Camera: person detected in morning hours (env-configurable)
            hour = datetime.now().hour
            if (
                WAKE_DETECT_HOUR_START <= hour < WAKE_DETECT_HOUR_END
                and len(parts) >= 6
                and parts[0] == "hems"
                and parts[1] == "sensors"
                and parts[3] == "camera"
            ):
                count = payload.get("person_count", payload.get("count", 0))
                if int(count) > 0:
                    wake_up_fired = True
                    if self._loop:
                        asyncio.run_coroutine_threadsafe(self.event_automation.trigger("wake_up"), self._loop)
                        if self.automation_engine:
                            asyncio.run_coroutine_threadsafe(
                                self.automation_engine.trigger_event("wake_up"), self._loop
                            )

        return wake_up_fired

    def _record_to_event_store(self, topic: str, payload, parts: list[str]) -> None:
        """S8: persist sensor telemetry + out-of-zone world events to event store."""
        if not self.event_writer:
            return
        if len(parts) >= 6 and parts[0] == "hems" and parts[1] == "sensors" and parts[3] == "sensor":
            channel = parts[5]
            value = payload.get(channel) or payload.get("value")
            if value is not None:
                # Input trust boundary: validate analog telemetry before it
                # is persisted to the event-store data mart (skews hourly
                # aggregates otherwise). EVENT/STATE channels carry
                # non-numeric payloads legitimately and are stored as-is.
                if classify_channel(channel) == ChannelType.ANALOG:
                    ok, coerced = validate_sensor_value(channel, value)
                    if not ok:
                        logger.warning(
                            "Rejected sensor value (not persisted): topic={} device={} raw={!r}",
                            topic,
                            parts[4],
                            value,
                        )
                        value = None
                    else:
                        value = coerced
                if value is not None:
                    self.event_writer.record_sensor(
                        zone=parts[2],
                        channel=channel,
                        value=value,
                        device_id=parts[4],
                        topic=topic,
                    )

        # Out-of-zone world events: shopping / gas / weather alerts / urgent news.
        # record_world_event dedupes on payload digest (5min), so retained
        # MQTT messages and repeat polls do not bloat the store.
        if len(parts) >= 3 and parts[0] == "hems":
            domain = parts[1]
            if (
                domain == "shopping"
                and len(parts) >= 3
                and parts[2]
                in (
                    "added",
                    "updated",
                    "purchased",
                )
            ):
                subject = None
                if isinstance(payload, dict):
                    subject = payload.get("name") or payload.get("item") or payload.get("id")
                self.event_writer.record_world_event(
                    source_type=f"shopping_{parts[2]}",
                    topic=topic,
                    payload=payload,
                    subject_ref=str(subject) if subject is not None else None,
                )
            elif domain == "gas" and len(parts) >= 3 and parts[2] != "bridge":
                subject = parts[2] if len(parts) >= 3 else None
                if len(parts) >= 4:
                    subject = f"{parts[2]}/{parts[3]}"
                self.event_writer.record_world_event(
                    source_type="gas",
                    topic=topic,
                    payload=payload,
                    subject_ref=subject,
                )
            elif domain == "weather" and len(parts) >= 3 and parts[2] == "alerts":
                self.event_writer.record_world_event(
                    source_type="weather_alert",
                    topic=topic,
                    payload=payload,
                    subject_ref=None,
                )
            elif domain == "news" and len(parts) >= 3 and parts[2] == "urgent":
                subject = None
                if isinstance(payload, dict):
                    subject = payload.get("title") or payload.get("url")
                self.event_writer.record_world_event(
                    source_type="news_urgent",
                    topic=topic,
                    payload=payload,
                    subject_ref=str(subject)[:200] if subject else None,
                )

    def _update_device_registry(self, topic: str, payload, parts: list[str]) -> None:
        """S9a: heartbeat update, Z2M bridge annotation, device auto-registration."""
        if "/heartbeat" in topic:
            # Canonical heartbeat: hems/sensors/{zone}/{device_type}/{device_id}/heartbeat
            if len(parts) >= 6 and parts[0] == "hems" and parts[1] == "sensors":
                self.device_registry.update_from_heartbeat(parts[4], payload)

        # Z2M bridge/devices retained → bulk annotation
        if topic == "zigbee2mqtt/bridge/devices" and isinstance(payload, list):
            if self.dashboard is not None and self._loop is not None:
                self._annotate_z2m_devices(payload)
            else:
                # Retained msg arrived before dashboard — stash for later
                self._z2m_bridge_devices_pending = payload

        # Device Registry auto-registration / refresh
        observation = parse_device_mqtt(topic, payload)
        if observation is not None and self.dashboard is not None and self._loop is not None:
            now = time.time()
            last = self._heartbeat_debounce.get(observation.device_id, 0.0)
            if now - last >= 10.0:  # throttle to max 1 heartbeat / 10s per device
                self._heartbeat_debounce[observation.device_id] = now
                asyncio.run_coroutine_threadsafe(self.dashboard.push_device_heartbeat(observation), self._loop)

    def _maybe_trigger_cycle(self) -> None:
        """S9b: trigger a cognitive cycle when world_model event counts changed.

        Must run AFTER all world_model mutations (S1/S5) — the comparison is a
        length diff over zone/domain event lists (design note §2-3).
        """
        current = {zid: len(z.events) for zid, z in self.world_model.zones.items()}
        if OPENCLAW_ENABLED:
            current["__pc__"] = len(self.world_model.pc_state.events)
            current["__services__"] = len(self.world_model.services_state.events)
        if OBSIDIAN_ENABLED:
            current["__knowledge__"] = len(self.world_model.knowledge_state.events)
        if GAS_ENABLED:
            current["__gas__"] = len(self.world_model.gas_state.events)
        if HA_ENABLED or SWITCHBOT_ENABLED:
            current["__home__"] = len(self.world_model.home_devices.events)
        if BIOMETRIC_ENABLED:
            current["__biometric__"] = len(self.world_model.biometric_state.events)
        if NEWS_ENABLED:
            current["__news__"] = len(self.world_model.news_state.events)
        if current != self._last_event_count:
            self._last_event_count = current
            self._cycle_triggered.set()

    def _annotate_z2m_devices(self, payload: list):
        """Parse Z2M bridge/devices and push annotations to backend."""
        observations = parse_z2m_bridge_devices(payload)
        for obs in observations:
            asyncio.run_coroutine_threadsafe(self.dashboard.push_device_heartbeat(obs), self._loop)
        logger.info(f"Z2M bridge/devices: annotated {len(observations)} devices")

    def _publish_mqtt(self, topic: str, payload: dict) -> None:
        """Fire-and-forget MQTT publish. Used by RuleEngine for side-channel requests
        like hems/perception/vlm/request where a rule needs to nudge another service
        without tying up the tool pipeline."""
        try:
            self.client.publish(topic, json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"MQTT publish failed ({topic}): {e}")
