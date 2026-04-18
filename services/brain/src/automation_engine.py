"""
AutomationEngine — evaluate AutomationRule triggers and fire actions.

Rules are pulled from backend on startup + every EVAL_REFRESH_SEC. Evaluation
tick runs every EVAL_INTERVAL_SEC and checks:

- sensor_threshold: {device_id, channel, op, value, sustain_s}
  fires when a sensor's last_value[channel] satisfies op+value for sustain_s continuously
- schedule: {cron: "0 7 * * *"} or {time: "07:00"}
  fires once per day at matching time (cron: minute granularity)
- event: {event: "wake_up"} — external trigger via trigger_event()
- device_state: {device_id, state_key, equals: true} — actuator state changed

Modes:
- direct: fire immediately when trigger holds
- llm_review: ask the LLM whether to fire (given context); useful for
  context-dependent decisions (e.g. skip watering if rain is forecast)
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime

import aiohttp
from loguru import logger

EVAL_INTERVAL_SEC = float(os.getenv("AUTOMATION_EVAL_INTERVAL", "15"))
EVAL_REFRESH_SEC = float(os.getenv("AUTOMATION_REFRESH_INTERVAL", "60"))
LLM_REVIEW_TIMEOUT = float(os.getenv("AUTOMATION_LLM_REVIEW_TIMEOUT", "30"))
BACKEND_URL = os.getenv("DASHBOARD_API_URL", os.getenv("BACKEND_URL", "http://backend:8000"))

_OPS = {
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


class AutomationEngine:
    def __init__(self, dispatcher, scene_executor, dashboard_client, llm_client, world_model, sanitizer):
        self.dispatcher = dispatcher
        self.scenes = scene_executor
        self.dashboard = dashboard_client
        self.llm_client = llm_client
        self.world_model = world_model
        self.sanitizer = sanitizer

        self._rules: list[dict] = []
        self._sustain_since: dict[int, float] = {}  # rule_id → first time trigger held
        self._scheduled_runs: dict[str, str] = {}  # "rule_id:time" → date
        self._task: asyncio.Task | None = None
        self._refresh_task: asyncio.Task | None = None
        self._running = False

    # ─── Lifecycle ──────────────────────────────────────────────────

    async def start(self):
        self._running = True
        await self.refresh()
        self._task = asyncio.create_task(self._loop())
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info(f"AutomationEngine started with {len(self._rules)} rules")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        if self._refresh_task:
            self._refresh_task.cancel()

    async def _loop(self):
        while self._running:
            try:
                await self.tick()
            except Exception as e:
                logger.warning(f"AutomationEngine tick error: {e}")
            await asyncio.sleep(EVAL_INTERVAL_SEC)

    async def _refresh_loop(self):
        while self._running:
            await asyncio.sleep(EVAL_REFRESH_SEC)
            try:
                await self.refresh()
            except Exception as e:
                logger.debug(f"Rule refresh error: {e}")

    async def refresh(self):
        """Pull rules from backend."""
        if self.dashboard is None or self.dashboard.session is None:
            return
        try:
            async with self.dashboard.session.get(
                f"{BACKEND_URL}/automations/",
                params={"enabled_only": "true"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    self._rules = await resp.json()
        except Exception as e:
            logger.debug(f"Automation refresh failed: {e}")

    # ─── Tick ───────────────────────────────────────────────────────

    async def tick(self):
        now = time.time()
        for rule in self._rules:
            if not rule.get("enabled", True):
                continue
            rule_id = rule["id"]
            # Cooldown check
            last_fired = rule.get("last_fired_at")
            cooldown = rule.get("cooldown_s", 600)
            if last_fired:
                try:
                    last_ts = datetime.fromisoformat(last_fired.replace("Z", "+00:00")).timestamp()
                    if now - last_ts < cooldown:
                        continue
                except (ValueError, TypeError):
                    pass

            ttype = rule.get("trigger_type")
            tcfg = rule.get("trigger_config") or {}
            should_fire = False

            if ttype == "sensor_threshold":
                should_fire = await self._check_sensor_threshold(rule_id, tcfg, now)
            elif ttype == "schedule":
                should_fire = self._check_schedule(rule_id, tcfg)
            elif ttype == "device_state":
                should_fire = await self._check_device_state(tcfg)
            # "event" triggers are external-only (handled by trigger_event)

            if should_fire:
                await self._fire(rule)

    async def _check_sensor_threshold(self, rule_id: int, cfg: dict, now: float) -> bool:
        device_id = cfg.get("device_id")
        channel = cfg.get("channel")
        value = cfg.get("value")
        op = cfg.get("op")
        sustain_s = int(cfg.get("sustain_s", 0))
        if not (device_id and channel and op in _OPS and value is not None):
            return False

        device = await self.dispatcher.lookup(device_id)
        if device is None:
            self._sustain_since.pop(rule_id, None)
            return False

        last_value = device.get("last_value") or {}
        reading = last_value.get(channel)
        if reading is None:
            self._sustain_since.pop(rule_id, None)
            return False

        try:
            holds = _OPS[op](float(reading), float(value))
        except (TypeError, ValueError):
            return False

        if not holds:
            self._sustain_since.pop(rule_id, None)
            return False

        if sustain_s <= 0:
            return True

        first_ts = self._sustain_since.get(rule_id)
        if first_ts is None:
            self._sustain_since[rule_id] = now
            return False
        return (now - first_ts) >= sustain_s

    def _check_schedule(self, rule_id: int, cfg: dict) -> bool:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")

        target = cfg.get("time")
        cron = cfg.get("cron")
        if target:
            key = f"{rule_id}:{target}"
            if current_time == target and self._scheduled_runs.get(key) != today:
                self._scheduled_runs[key] = today
                return True
            return False

        if cron:
            # Minimal cron support: "M H * * *" (minute hour everyday)
            parts = cron.split()
            if len(parts) < 2:
                return False
            m, h = parts[0], parts[1]
            if m == "*" or h == "*":
                # Don't support wildcards in MVP — schedule noisy
                return False
            try:
                target_str = f"{int(h):02d}:{int(m):02d}"
            except ValueError:
                return False
            key = f"{rule_id}:{target_str}"
            if current_time == target_str and self._scheduled_runs.get(key) != today:
                self._scheduled_runs[key] = today
                return True

        return False

    async def _check_device_state(self, cfg: dict) -> bool:
        device_id = cfg.get("device_id")
        state_key = cfg.get("state_key")
        target = cfg.get("equals")
        if not device_id or not state_key:
            return False
        device = await self.dispatcher.lookup(device_id)
        if device is None:
            return False
        return (device.get("last_state") or {}).get(state_key) == target

    # ─── Firing ─────────────────────────────────────────────────────

    async def trigger_event(self, event_name: str):
        """Fire all rules with trigger_type='event' matching event_name."""
        for rule in self._rules:
            if not rule.get("enabled", True):
                continue
            if rule.get("trigger_type") != "event":
                continue
            cfg = rule.get("trigger_config") or {}
            if cfg.get("event") == event_name:
                await self._fire(rule)

    async def _fire(self, rule: dict):
        rule_id = rule["id"]
        mode = rule.get("mode", "direct")

        # Optional LLM review
        if mode == "llm_review":
            proceed, reason = await self._llm_review(rule)
            if not proceed:
                logger.info(f"Rule#{rule_id} '{rule.get('name')}' skipped by llm_review: {reason}")
                return

        actions = rule.get("actions") or []
        if not actions:
            logger.debug(f"Rule#{rule_id} fired but has no actions")
            return

        # Execute via scene executor (same action schema)
        result = await self.scenes.execute(actions)
        self._sustain_since.pop(rule_id, None)

        # Update fire stats via backend
        await self._record_fire(rule_id)

        logger.info(
            f"Rule#{rule_id} '{rule.get('name')}' fired: {result['executed']} actions, errors={result['errors']}"
        )

    async def _llm_review(self, rule: dict) -> tuple[bool, str]:
        """Ask the LLM whether to fire this rule."""
        if self.llm_client is None:
            return True, "llm unavailable, defaulting to direct fire"

        world_context = ""
        try:
            world_context = self.world_model.get_llm_context()[:2000]
        except Exception:
            pass

        prompt = (
            f"以下のHEMS自動化ルールを発火すべきか判断してください。"
            f"通常は発火が適切ですが、現在の状況 (天気、在室等) で発火すべきでない理由があればskip。\n\n"
            f"## ルール\n"
            f"名前: {rule.get('name')}\n"
            f"説明: {rule.get('description') or '(未設定)'}\n"
            f"トリガー: {rule.get('trigger_type')} / {rule.get('trigger_config')}\n"
            f"アクション: {rule.get('actions')}\n\n"
            f"## 現在の自宅状態\n{world_context}\n\n"
            f"回答形式は最初の1行目に fire または skip、2行目以降に短い理由。"
        )

        try:
            response = await asyncio.wait_for(
                self.llm_client.chat([{"role": "user", "content": prompt}]),
                timeout=LLM_REVIEW_TIMEOUT,
            )
            text = (response or "").strip()
            first_line = text.splitlines()[0].strip().lower() if text else ""
            reason = text[:300]
            if first_line.startswith("fire"):
                return True, reason
            if first_line.startswith("skip"):
                return False, reason
            # Ambiguous response — default to skip (safe)
            logger.warning(f"llm_review ambiguous response: {text[:100]}")
            return False, f"ambiguous response: {first_line}"
        except TimeoutError:
            logger.warning("llm_review timeout — defaulting to skip")
            return False, "llm timeout"
        except Exception as e:
            logger.warning(f"llm_review error: {e}")
            return False, str(e)

    async def _record_fire(self, rule_id: int):
        if self.dashboard is None or self.dashboard.session is None:
            return
        # Find rule in memory to compute fire_count
        rule = next((r for r in self._rules if r["id"] == rule_id), None)
        if rule is None:
            return
        new_count = (rule.get("fire_count") or 0) + 1
        rule["fire_count"] = new_count
        rule["last_fired_at"] = datetime.now(UTC).isoformat()
        try:
            async with self.dashboard.session.put(
                f"{BACKEND_URL}/automations/{rule_id}/fire",
                json={
                    "last_fired_at": rule["last_fired_at"],
                    "fire_count": new_count,
                },
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"record_fire failed: HTTP {resp.status}")
        except Exception as e:
            logger.debug(f"record_fire error: {e}")

    # ─── Dry-run evaluation (for /automations/{id}/test) ────────────

    async def evaluate_trigger(self, trigger_type: str, trigger_config: dict) -> dict:
        """Evaluate a trigger condition without firing. Used by backend /test."""
        if trigger_type == "sensor_threshold":
            cfg = trigger_config
            device_id = cfg.get("device_id", "")
            channel = cfg.get("channel", "")
            op = cfg.get("op", "")
            value = cfg.get("value")
            device = await self.dispatcher.lookup(device_id) if device_id else None
            if device is None:
                return {"would_fire": False, "reason": f"device '{device_id}' not registered", "sampled_value": None}
            reading = (device.get("last_value") or {}).get(channel)
            if reading is None:
                return {"would_fire": False, "reason": f"no reading for {device_id}.{channel}", "sampled_value": None}
            try:
                holds = _OPS.get(op, lambda a, b: False)(float(reading), float(value))
            except (TypeError, ValueError):
                holds = False
            return {
                "would_fire": holds,
                "reason": (f"{device_id}.{channel}={reading} {op} {value} → {'holds' if holds else 'does not hold'}"),
                "sampled_value": reading,
            }
        if trigger_type == "schedule":
            target = trigger_config.get("time") or trigger_config.get("cron", "")
            return {
                "would_fire": False,
                "reason": f"schedule '{target}' — test only confirms config; fires at time match",
                "sampled_value": None,
            }
        if trigger_type == "event":
            return {
                "would_fire": False,
                "reason": f"event '{trigger_config.get('event')}' — fires only when event occurs",
                "sampled_value": None,
            }
        if trigger_type == "device_state":
            holds = await self._check_device_state(trigger_config)
            return {
                "would_fire": holds,
                "reason": f"device_state held={holds}",
                "sampled_value": None,
            }
        return {"would_fire": False, "reason": f"unknown trigger_type {trigger_type}", "sampled_value": None}
