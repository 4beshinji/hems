"""
HEMS Lite Sentinel — main watchdog loop.
Subscribes to MQTT, evaluates rules, detects gray zones, escalates to LLM.
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, date

import paho.mqtt.client as mqtt
from loguru import logger

from config import (
    MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS,
    NOTIFIER_URL, SITE_ID, SITE_NAME, MODE,
    CYCLE_INTERVAL, DAILY_SUMMARY_ENABLED, DAILY_SUMMARY_TIME,
    NOTIFY_MIN_LEVEL,
)
from state import OccupantState
from rules import RuleEngine, Alert, AlertLevel
from gray_zone import GrayZoneDetector, GrayZoneEvent
from escalation import Escalator, EscalationVerdict
from db import SentinelDB

import httpx

# Configure logging
logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))

# Map string level names to AlertLevel
LEVEL_MAP = {
    "CRITICAL": AlertLevel.CRITICAL,
    "HIGH": AlertLevel.HIGH,
    "NORMAL": AlertLevel.NORMAL,
    "INFO": AlertLevel.INFO,
}


class Sentinel:
    def __init__(self):
        self.state = OccupantState()
        self.rules = RuleEngine()
        self.gray_zone = GrayZoneDetector()
        self.escalator = Escalator()
        self.db = SentinelDB()
        self.http = httpx.AsyncClient(timeout=10)

        self._mqtt_client: mqtt.Client | None = None
        self._mqtt_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._last_summary_date: date | None = None

    async def start(self):
        logger.info(f"Sentinel starting: site={SITE_ID}, mode={MODE}")
        await self.db.init()
        self._setup_mqtt()
        self._running = True

        tasks = [
            asyncio.create_task(self._process_loop()),
            asyncio.create_task(self._summary_scheduler()),
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self):
        self._running = False
        if self._mqtt_client:
            self._mqtt_client.disconnect()
            self._mqtt_client.loop_stop()
        await self.escalator.close()
        await self.http.aclose()
        await self.db.close()
        logger.info("Sentinel shutdown complete")

    # --- MQTT ---

    def _setup_mqtt(self):
        client = mqtt.Client(client_id=f"sentinel-{SITE_ID}", protocol=mqtt.MQTTv5)
        if MQTT_USER:
            client.username_pw_set(MQTT_USER, MQTT_PASS)

        client.on_connect = self._on_connect
        client.on_message = self._on_message

        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
        self._mqtt_client = client

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        logger.info(f"MQTT connected (rc={rc})")
        # Biometric data
        client.subscribe("hems/personal/biometrics/#")
        # Perception / activity
        client.subscribe("office/+/camera/+/status")
        client.subscribe("office/+/activity/+")
        # Environment sensors
        client.subscribe("office/+/sensor/#")
        # Bridge status
        client.subscribe("hems/+/bridge/status")
        client.subscribe("hems/perception/bridge/status")
        # Home assistant
        client.subscribe("hems/home/#")

    def _on_message(self, client, userdata, msg):
        try:
            self._mqtt_queue.put_nowait((msg.topic, msg.payload))
        except asyncio.QueueFull:
            pass

    # --- Main loop ---

    async def _process_loop(self):
        while self._running:
            # Drain MQTT queue
            while not self._mqtt_queue.empty():
                try:
                    topic, payload = self._mqtt_queue.get_nowait()
                    self._handle_mqtt(topic, payload)
                except asyncio.QueueEmpty:
                    break

            # Evaluate rules
            alerts = self.rules.evaluate(self.state)

            # Send clear-threshold alerts
            for alert in alerts:
                await self._handle_alert(alert)

            # Detect gray zones
            gray_events = self.gray_zone.evaluate(self.state)

            # Escalate gray zones to LLM
            for event in gray_events:
                await self._handle_gray_zone(event)

            await asyncio.sleep(CYCLE_INTERVAL)

    def _handle_mqtt(self, topic: str, payload: bytes):
        """Parse MQTT message and update state."""
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        parts = topic.split("/")

        # Biometric: hems/personal/biometrics/{provider}/{metric}
        if topic.startswith("hems/personal/biometrics/"):
            if len(parts) >= 5:
                metric = parts[4]
                if metric == "bridge":
                    return
                self._handle_biometric(metric, data)

        # Camera status: office/{zone}/camera/{cam_id}/status
        elif len(parts) >= 5 and parts[2] == "camera" and parts[4] == "status":
            zone_id = parts[1]
            self.state.update_activity(
                zone_id=zone_id,
                person_count=data.get("person_count", 0),
                posture=data.get("posture", ""),
                activity_level=data.get("activity_level", 0.0),
                posture_duration_sec=data.get("posture_duration_sec", 0.0),
            )

        # Activity: office/{zone}/activity/{monitor_id}
        elif len(parts) >= 4 and parts[2] == "activity":
            zone_id = parts[1]
            self.state.update_activity(
                zone_id=zone_id,
                person_count=data.get("person_count", 0),
                posture=data.get("posture", data.get("activity_class", "")),
                activity_level=data.get("activity_level", 0.0),
                posture_duration_sec=data.get("posture_duration_sec", 0.0),
            )

        # Environment: office/{zone}/sensor/{device_id}/{channel}
        elif len(parts) >= 5 and parts[2] == "sensor":
            zone_id = parts[1]
            channel = parts[4]
            value = data.get("value", data.get(channel))
            if value is not None:
                self.state.update_environment(zone_id, **{channel: float(value)})

        # Bridge status
        elif topic.endswith("/bridge/status"):
            if "biometric" in topic:
                self.state.biometric_connected = data.get("status") == "online"
            elif "perception" in topic:
                self.state.perception_connected = data.get("status") == "online"
            elif "home" in topic or "ha" in topic:
                self.state.ha_connected = data.get("status") == "online"

    def _handle_biometric(self, metric: str, data: dict):
        """Process biometric MQTT message."""
        if metric == "heart_rate":
            bpm = data.get("bpm", data.get("value"))
            if bpm is not None:
                self.state.update_biometric("heart_rate", float(bpm))
        elif metric == "spo2":
            pct = data.get("percent", data.get("value"))
            if pct is not None:
                self.state.update_biometric("spo2", float(pct))
        elif metric == "stress":
            level = data.get("level", data.get("value"))
            if level is not None:
                self.state.update_biometric("stress", float(level))
        elif metric == "fatigue":
            score = data.get("score", data.get("value"))
            if score is not None:
                self.state.update_biometric("fatigue", float(score))
        elif metric == "sleep":
            self.state.update_sleep(
                stage=data.get("stage", ""),
                duration=data.get("duration_hours", 0.0),
                quality=data.get("quality_score", 0),
            )
        elif metric == "activity":
            steps = data.get("steps", 0)
            goal = data.get("steps_goal", 0)
            if steps:
                self.state.update_steps(int(steps), int(goal) if goal else 0)
        elif metric == "steps":
            steps = data.get("value", data.get("steps", 0))
            if steps:
                self.state.update_steps(int(steps))
        else:
            # Generic: hrv, body_temp, respiratory_rate, etc
            value = data.get("value", data.get("rmssd_ms", data.get("celsius",
                      data.get("breaths_per_minute"))))
            if value is not None:
                self.state.update_biometric(metric, float(value))

    # --- Alert handling ---

    async def _handle_alert(self, alert: Alert):
        """Process a rule-fired alert: log, notify if above threshold."""
        now = time.time()
        min_level = LEVEL_MAP.get(NOTIFY_MIN_LEVEL, AlertLevel.HIGH)
        should_notify = alert.level >= min_level

        data_json = json.dumps(alert.data or {}, ensure_ascii=False)
        await self.db.log_alert(
            timestamp=now,
            level=alert.level.name,
            rule_id=alert.rule_id,
            title=alert.title,
            body=alert.body,
            source=alert.source,
            zone=alert.zone,
            data_json=data_json,
            notified=should_notify,
        )

        if should_notify:
            await self._send_notification(
                level=alert.level.name,
                title=alert.title,
                body=alert.body,
                source=alert.source,
                zone=alert.zone,
            )

    async def _handle_gray_zone(self, event: GrayZoneEvent):
        """Escalate gray zone to LLM, then decide."""
        result = await self.escalator.evaluate(event, self.state)

        if result is None:
            # LLM unavailable or budget exhausted — log only
            logger.debug(f"Gray zone logged (no LLM): {event.pattern}")
            await self.db.log_alert(
                timestamp=time.time(),
                level="GRAY",
                rule_id=f"gray_{event.pattern}",
                title=f"グレーゾーン: {event.pattern}",
                body=event.description,
                source="gray_zone",
                data_json=json.dumps({"signals": event.signals}, ensure_ascii=False),
                escalated=False,
            )
            return

        # Log with LLM verdict
        await self.db.log_alert(
            timestamp=time.time(),
            level=result.level,
            rule_id=f"gray_{event.pattern}",
            title=f"グレーゾーン: {event.pattern}",
            body=event.description,
            source="gray_zone",
            data_json=json.dumps({"signals": event.signals}, ensure_ascii=False),
            escalated=True,
            notified=(result.verdict == EscalationVerdict.NOTIFY),
            llm_verdict=result.verdict,
            llm_reason=result.reason,
        )

        if result.verdict == EscalationVerdict.NOTIFY:
            await self._send_notification(
                level=result.level,
                title=f"[AI判定] {event.pattern}",
                body=result.message or result.reason,
                source="gray_zone_llm",
            )
            logger.info(f"Gray zone NOTIFY: {event.pattern} — {result.reason}")
        elif result.verdict == EscalationVerdict.WATCH:
            logger.info(f"Gray zone WATCH: {event.pattern} — {result.reason}")
        else:
            logger.info(f"Gray zone IGNORE: {event.pattern} — {result.reason}")

    # --- Notification ---

    async def _send_notification(self, level: str, title: str, body: str,
                                 source: str = "", zone: str = ""):
        """Send alert to notifier service."""
        payload = {
            "level": level,
            "title": title,
            "body": body,
            "source": source,
            "zone": zone,
            "site_id": SITE_ID,
            "site_name": SITE_NAME,
            "timestamp": time.time(),
        }
        try:
            resp = await self.http.post(f"{NOTIFIER_URL}/api/notify", json=payload)
            if resp.status_code != 200:
                logger.error(f"Notifier error: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    # --- Daily summary ---

    async def _summary_scheduler(self):
        """Schedule daily summary at configured time."""
        if not DAILY_SUMMARY_ENABLED:
            return

        h, m = DAILY_SUMMARY_TIME.split(":")
        target_hour, target_min = int(h), int(m)

        while self._running:
            now = datetime.now()
            today = now.date()

            if (now.hour == target_hour
                    and now.minute == target_min
                    and self._last_summary_date != today):
                await self._send_daily_summary()
                self._last_summary_date = today

            await asyncio.sleep(30)

    async def _send_daily_summary(self):
        """Generate and send daily summary."""
        now = time.time()
        since = now - 86400  # past 24h
        alerts = await self.db.get_alerts_since(since)

        # Count by level
        counts = {"CRITICAL": 0, "HIGH": 0, "NORMAL": 0, "INFO": 0, "GRAY": 0}
        for a in alerts:
            lvl = a["level"]
            counts[lvl] = counts.get(lvl, 0) + 1

        # Build summary
        s = self.state
        lines = [
            f"[{SITE_NAME}] 日次レポート ({datetime.now().strftime('%m/%d')})",
            "",
        ]

        # Biometrics
        if s.heart_rate.value is not None:
            lines.append(f"HR: {s.heart_rate.value:.0f}bpm")
        if s.spo2.value is not None:
            lines.append(f"SpO2: {s.spo2.value:.0f}%")

        # Sleep
        if s.sleep.duration_hours > 0:
            lines.append(
                f"Sleep: {s.sleep.duration_hours:.1f}h "
                f"(quality: {s.sleep.quality_score}/100)"
            )

        # Activity
        if s.activity.steps > 0:
            lines.append(f"Steps: {s.activity.steps}")

        # Environment
        for zid, zone in s.zones.items():
            env = zone.environment
            if env.temperature is not None:
                lines.append(f"{zid}: {env.temperature:.1f}C / {env.humidity:.0f}%"
                             if env.humidity else f"{zid}: {env.temperature:.1f}C")

        # Alert count
        lines.append("")
        total_alerts = sum(counts.values())
        if total_alerts > 0:
            parts = []
            for lvl in ("CRITICAL", "HIGH", "NORMAL", "GRAY"):
                if counts.get(lvl, 0) > 0:
                    parts.append(f"{lvl}: {counts[lvl]}")
            lines.append(f"Alerts (24h): {', '.join(parts)}")

            # List critical/high alerts
            important = [a for a in alerts if a["level"] in ("CRITICAL", "HIGH")]
            for a in important[:5]:
                ts = datetime.fromtimestamp(a["timestamp"]).strftime("%H:%M")
                lines.append(f"  {ts} [{a['level']}] {a['title']}")
        else:
            lines.append("Alerts: none")

        # LLM budget
        if self.escalator.llm_available:
            lines.append(f"LLM budget remaining: {self.escalator.budget_remaining}")

        summary = "\n".join(lines)

        # Save to DB
        await self.db.save_daily_summary(
            datetime.now().strftime("%Y-%m-%d"),
            json.dumps({"text": summary}, ensure_ascii=False),
        )

        # Send as notification
        await self._send_notification(
            level="INFO",
            title=f"日次レポート ({datetime.now().strftime('%m/%d')})",
            body=summary,
            source="daily_summary",
        )
        logger.info("Daily summary sent")


async def main():
    sentinel = Sentinel()
    try:
        await sentinel.start()
    except KeyboardInterrupt:
        await sentinel.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
