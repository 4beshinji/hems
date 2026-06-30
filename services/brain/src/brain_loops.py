import asyncio
import json
import os
import time
from datetime import datetime

from loguru import logger

from brain_constants import (
    BIOMETRIC_ENABLED,
    EFFICACY_EVAL_INTERVAL,
    GAS_ENABLED,
    HA_ENABLED,
    NEWS_ENABLED,
    OBSIDIAN_ENABLED,
    OPENCLAW_ENABLED,
    SCHEDULE_STATE_PATH,
    SECONDS_PER_DAY,
)


class BackgroundLoopsMixin:
    # Phase 2: map trigger metric channels to adaptive threshold metric keys.
    _CHANNEL_TO_METRIC_KEYS: dict[str, list[str]] = {
        "co2": ["co2_high"],
        "temperature": ["temp_high", "temp_low"],
        "humidity": ["humidity_high", "humidity_low"],
        "pm25": ["pm25_high"],
    }

    def _metric_keys_for_channel(self, channel: str) -> list[str]:
        return self._CHANNEL_TO_METRIC_KEYS.get(channel, [])

    async def _push_all_snapshots(self):
        """Push all domain snapshots to backend for frontend consumption."""
        await self.dashboard.push_zone_snapshot(self.world_model)
        if OPENCLAW_ENABLED:
            await self.dashboard.push_pc_snapshot(self.world_model)
        if OPENCLAW_ENABLED and self.world_model.services_state.services:
            await self.dashboard.push_services_snapshot(self.world_model)
        if OBSIDIAN_ENABLED:
            await self.dashboard.push_knowledge_snapshot(self.world_model)
        if GAS_ENABLED:
            await self.dashboard.push_gas_snapshot(self.world_model)
        if BIOMETRIC_ENABLED:
            await self.dashboard.push_biometric_snapshot(self.world_model)
        # Always push: also carries multi-source presence inference (camera+PIR+PC+biometric)
        await self.dashboard.push_perception_snapshot(self.world_model)
        if HA_ENABLED:
            await self.dashboard.push_home_snapshot(self.world_model)
        # Always push weather (weather-bridge is always-on, no profile)
        await self.dashboard.push_weather_snapshot(self.world_model)
        if NEWS_ENABLED:
            await self.dashboard.push_news_snapshot(self.world_model)
        await self.dashboard.push_brain_snapshot(
            self.power_mode_manager.get_status(),
            last_cycle=self._last_cycle_summary,
        )
        # Track bridge_connected transitions for SLA log
        await self._track_bridge_transitions()

    async def _track_bridge_transitions(self):
        """Detect and log per-bridge state transitions for SLA history.

        Maintains a 24h rolling disconnect count per service; when ≥5 disconnects
        in 24h fires a once-per-day speak alert (instability warning).
        State is declared in Brain.__init__ (_bridge_* dicts).
        """
        wm = self.world_model
        now_ts = time.time()
        current = {
            "biometric": wm.biometric_state.bridge_connected,
            "perception": wm.perception_state.bridge_connected if hasattr(wm, "perception_state") else None,
            "ha": wm.home_devices.bridge_connected,
            "gas": wm.gas_state.bridge_connected,
            "news": wm.news_state.bridge_connected,
            "knowledge": wm.knowledge_state.bridge_connected,
            "external_knowledge": wm.knowledge_state.external_bridge_connected,
            "services": wm.services_state.bridge_connected if hasattr(wm.services_state, "bridge_connected") else None,
        }
        for service, connected in current.items():
            if connected is None:
                continue
            prev = self._bridge_state_cache.get(service)
            if prev is None:
                self._bridge_state_cache[service] = connected
                continue
            if prev != connected:
                self._bridge_state_cache[service] = connected
                try:
                    await self.dashboard.push_bridge_status_event(service, connected)
                except Exception as e:
                    logger.debug(f"Bridge status track error for {service}: {e}")

                if not connected:
                    # Add disconnect timestamp; trim old entries beyond 24h
                    history = self._bridge_disconnect_history.setdefault(service, [])
                    history.append(now_ts)
                    cutoff = now_ts - SECONDS_PER_DAY
                    self._bridge_disconnect_history[service] = [t for t in history if t >= cutoff]

                    if (
                        len(self._bridge_disconnect_history[service]) >= 5
                        and now_ts - self._bridge_outage_alert_sent.get(service, 0) >= SECONDS_PER_DAY
                    ):
                        self._bridge_outage_alert_sent[service] = now_ts
                        try:
                            await self.tool_executor.execute(
                                "speak",
                                {
                                    "message": (
                                        f"{service} ブリッジが過去24時間で"
                                        f"{len(self._bridge_disconnect_history[service])}回切断されています。"
                                        f"ネットワーク状態を確認してください。"
                                    ),
                                    "zone": "home",
                                    "tone": "alert",
                                },
                            )
                        except Exception as e:
                            logger.debug(f"Bridge outage alert speak error: {e}")

    def _load_schedule_state(self):
        """Load schedule learner state from disk."""
        if not self.schedule_learner:
            return
        try:
            with open(SCHEDULE_STATE_PATH) as f:
                data = json.load(f)
            self.schedule_learner.load_state(data)
            logger.info(f"Schedule learner state loaded from {SCHEDULE_STATE_PATH}")
        except FileNotFoundError:
            logger.debug("No schedule learner state file found (first run)")
        except Exception as e:
            logger.warning(f"Schedule learner state load failed: {e}")

    def _save_schedule_state(self):
        """Save schedule learner state to disk."""
        if not self.schedule_learner:
            return
        try:
            os.makedirs(os.path.dirname(SCHEDULE_STATE_PATH), exist_ok=True)
            data = self.schedule_learner.save_state()
            with open(SCHEDULE_STATE_PATH, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.debug(f"Schedule state save failed: {e}")

    async def _maybe_daily_maintenance(self):
        """Run rule_promoter + ack_learner + adaptive threshold flush once per day."""
        now = datetime.now()
        if now.hour != 3:
            return
        today = now.strftime("%Y-%m-%d")
        if self._daily_maintenance_date == today:
            return
        self._daily_maintenance_date = today
        try:
            if self._rule_promoter:
                n = await self._rule_promoter.run()
                if n:
                    logger.info("[DailyMaint] rule_promoter promoted %d entries", n)
            if self._ack_learner:
                n = await self._ack_learner.run()
                if n:
                    logger.info("[DailyMaint] ack_learner adjusted %d entries", n)
            await self._run_adaptive_threshold_maintenance()
        except Exception as e:
            logger.warning(f"Daily maintenance error: {e}")

    async def _run_adaptive_threshold_maintenance(self):
        """Flush pending drift proposals to backend and reload approved offsets."""
        if self.adaptive_threshold_manager is None or self.threshold_client is None:
            return
        try:
            proposals = self.adaptive_threshold_manager.flush_proposals()
            for proposal in proposals:
                try:
                    await self.threshold_client.create_proposal(proposal)
                    logger.info(
                        "[DailyMaint] created threshold proposal: %s",
                        proposal.get("metric_key"),
                    )
                except Exception as e:
                    logger.warning(f"[DailyMaint] failed to create threshold proposal: {e}")

            # Reload approved/auto_applied adjustments from backend.
            adjustments = await self.threshold_client.list_adjustments()
            if self.adaptive_thresholds is not None:
                for adj in adjustments:
                    metric_key = adj.get("metric_key")
                    offset = adj.get("offset", 0.0)
                    if metric_key:
                        self.adaptive_thresholds.set_offset(metric_key, float(offset))
        except Exception as e:
            logger.warning(f"[DailyMaint] adaptive threshold maintenance error: {e}")

    async def _efficacy_eval_loop(self):
        """Score completed environment interventions (Group D).

        For each completed-but-unverdicted row whose post-window has elapsed,
        average the targeted metric over the window, compute a comfort-band
        verdict, persist it, and stash a short summary for the cognitive cycle.
        """
        from efficacy import compute_verdict

        while True:
            await asyncio.sleep(EFFICACY_EVAL_INTERVAL)
            if not self.event_writer:
                continue
            try:
                pending = await self.event_writer.fetch_pending_interventions()
                for row in pending:
                    post = await self.event_writer.compute_post_value(
                        zone=row["zone"],
                        channel=row["trigger_metric"],
                        start=row["completed_at"],
                        window_sec=row["window_sec"],
                    )
                    verdict = compute_verdict(row["trigger_metric"], row["baseline_value"], post)
                    await self.event_writer.record_intervention_verdict(row["id"], post, verdict)
                    self._recent_efficacy_verdicts.append(
                        {
                            "zone": row["zone"],
                            "metric": row["trigger_metric"],
                            "baseline": row["baseline_value"],
                            "post": post,
                            "verdict": verdict,
                            "time": time.time(),
                        }
                    )

                    # Phase 2: nudge threshold offsets based on efficacy verdict.
                    if self.threshold_adjuster is not None and self.adaptive_thresholds is not None:
                        metric = row["trigger_metric"]
                        for metric_key in self._metric_keys_for_channel(metric):
                            current_offset = self.adaptive_thresholds.get_offset(metric_key)
                            new_offset = self.threshold_adjuster.compute_offset(
                                current_offset,
                                efficacy_verdict=verdict,
                            )
                            self.adaptive_thresholds.set_offset(metric_key, new_offset)
                            logger.info(
                                "Threshold offset adjusted from efficacy: %s %s -> %s",
                                metric_key,
                                current_offset,
                                new_offset,
                            )

                    logger.info(
                        f"Efficacy verdict: zone={row['zone']} metric={row['trigger_metric']} "
                        f"baseline={row['baseline_value']} post={post} -> {verdict}"
                    )
                # Keep only the last ~10 from the past 24h for context injection.
                cutoff = time.time() - SECONDS_PER_DAY
                self._recent_efficacy_verdicts = [v for v in self._recent_efficacy_verdicts if v["time"] > cutoff][-10:]
            except Exception as e:
                logger.error(f"Efficacy eval loop error: {e}")
