"""Manage drift trackers and propose threshold adjustments."""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from adaptive_thresholds.tracker import DriftResult, MetricDriftTracker
from rules.config import RuleThresholds

# Metrics that are safe to adapt. Life-safety metrics are intentionally excluded.
ADAPTABLE_METRICS = {
    "co2_high",
    "temp_high",
    "temp_low",
    "humidity_high",
    "humidity_low",
    "pm25_high",
}

# Per-metric clamp for proposed offset (absolute units).
DEFAULT_CLAMP = (-5.0, 5.0)
METRIC_CLAMPS: dict[str, tuple[float, float]] = {
    "co2_high": (-200.0, 200.0),
    "temp_high": (-3.0, 3.0),
    "temp_low": (-3.0, 3.0),
    "humidity_high": (-10.0, 10.0),
    "humidity_low": (-10.0, 10.0),
    "pm25_high": (-10.0, 10.0),
}

# Sensor channel -> metric keys we track for drift.
SENSOR_CHANNEL_METRICS: dict[str, list[str]] = {
    "co2": ["co2_high"],
    "temperature": ["temp_high", "temp_low"],
    "humidity": ["humidity_high", "humidity_low"],
    "pm25": ["pm25_high"],
}


class AdaptiveThresholdManager:
    """Owns MetricDriftTracker instances and produces drift proposals."""

    def __init__(
        self,
        thresholds: RuleThresholds,
        event_writer: Any | None = None,
        backend_client: Any | None = None,
    ):
        self.thresholds = thresholds
        self.event_writer = event_writer
        self.backend_client = backend_client
        self._trackers: dict[str, MetricDriftTracker] = {}
        self._offsets: dict[str, float] = {}
        self._pending_proposals: list[dict] = []

    def _get_tracker(self, metric_key: str) -> MetricDriftTracker:
        if metric_key not in self._trackers:
            clamp = METRIC_CLAMPS.get(metric_key, DEFAULT_CLAMP)
            self._trackers[metric_key] = MetricDriftTracker(
                metric_key=metric_key,
                detector=os.getenv("HEMS_DRIFT_DETECTOR", "adwin"),
                delta=float(os.getenv("HEMS_DRIFT_DELTA", "0.002")),
                min_samples=int(os.getenv("HEMS_DRIFT_MIN_SAMPLES", "30")),
                clamp=clamp,
            )
        return self._trackers[metric_key]

    def _base_value(self, metric_key: str) -> float | None:
        """Return the static base threshold for a metric key."""
        return getattr(self.thresholds, metric_key, None)

    def _effective_threshold(self, metric_key: str) -> float | None:
        base = self._base_value(metric_key)
        if base is None:
            return None
        return base + self._offsets.get(metric_key, 0.0)

    def feed(
        self,
        channel: str,
        value: float,
    ) -> list[DriftResult]:
        """Feed a sensor reading to all trackers tied to the channel."""
        results: list[DriftResult] = []
        metric_keys = SENSOR_CHANNEL_METRICS.get(channel, [])
        for metric_key in metric_keys:
            if metric_key not in ADAPTABLE_METRICS:
                continue
            tracker = self._get_tracker(metric_key)
            current = self._effective_threshold(metric_key)
            result = tracker.update(value, current_threshold=current)
            if result.drift_detected:
                proposal = self._build_proposal(metric_key, result)
                self._pending_proposals.append(proposal)
                self._record_drift(proposal, tracker.get_state())
            results.append(result)
        return results

    def _build_proposal(
        self,
        metric_key: str,
        result: DriftResult,
    ) -> dict[str, Any]:
        base = self._base_value(metric_key)
        old = result.old_threshold
        proposed = result.proposed_threshold
        return {
            "metric_key": metric_key,
            "detector": "adwin",
            "old_value": old if old is not None else base,
            "proposed_value": proposed,
            "reason": "drift",
            "status": "proposed",
            "context_json": {
                "estimation": result.estimation,
                "variance": result.variance,
                "width": result.width,
                "base_value": base,
            },
        }

    def _record_drift(
        self,
        proposal: dict[str, Any],
        detector_state: dict[str, Any],
    ) -> None:
        if self.event_writer is not None:
            try:
                self.event_writer.record_drift_detection(
                    metric_key=proposal["metric_key"],
                    detector=proposal["detector"],
                    old_threshold=proposal["old_value"],
                    proposed_threshold=proposal["proposed_value"],
                    detector_state=detector_state,
                )
            except Exception as e:
                logger.debug(f"Failed to record drift detection: {e}")

    def flush_proposals(self) -> list[dict[str, Any]]:
        """Return and clear pending proposals; caller posts them to backend."""
        proposals = self._pending_proposals
        self._pending_proposals = []
        return proposals

    def load_adjustments(self, adjustments: list[dict[str, Any]]) -> None:
        """Apply already-approved offsets (e.g. fetched from backend on startup)."""
        for adj in adjustments:
            metric_key = adj.get("metric_key")
            offset = adj.get("offset", 0.0)
            if metric_key and metric_key in ADAPTABLE_METRICS:
                self._offsets[metric_key] = float(offset)
                logger.info(
                    "Loaded threshold adjustment for %s: offset=%s",
                    metric_key,
                    offset,
                )

    def set_offset(self, metric_key: str, offset: float) -> None:
        """Apply an offset directly (used by ThresholdAdjuster / daily recal)."""
        if metric_key not in ADAPTABLE_METRICS:
            return
        clamp = METRIC_CLAMPS.get(metric_key, DEFAULT_CLAMP)
        offset = max(clamp[0], min(clamp[1], offset))
        self._offsets[metric_key] = offset

    def get_offset(self, metric_key: str) -> float:
        return self._offsets.get(metric_key, 0.0)

    def get_effective(self, metric_key: str) -> float | None:
        return self._effective_threshold(metric_key)

    def get_state(self) -> dict[str, Any]:
        return {
            "offsets": dict(self._offsets),
            "trackers": {k: v.get_state() for k, v in self._trackers.items()},
        }
