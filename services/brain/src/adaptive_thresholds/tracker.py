"""Online drift tracker for a single metric using River."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger
from river import drift


@dataclass
class DriftResult:
    drift_detected: bool = False
    estimation: float | None = None
    variance: float | None = None
    width: int | None = None
    old_threshold: float | None = None
    proposed_threshold: float | None = None


class MetricDriftTracker:
    """Wrap River drift detector for one metric key.

    Tracks the sensor value stream and reports when the distribution has
    shifted enough to warrant a threshold review. Proposed thresholds are
    computed relative to a baseline estimation captured at construction or
    last reset, keeping adaptation bounded by the metric's configured clamp.
    """

    DETECTOR_CLASSES = {
        "adwin": drift.ADWIN,
        "pagehinkley": drift.PageHinkley,
    }

    def __init__(
        self,
        metric_key: str,
        detector: str = "adwin",
        delta: float = 0.002,
        min_samples: int = 30,
        clamp: tuple[float, float] = (-5.0, 5.0),
    ):
        self.metric_key = metric_key
        self.detector_name = detector
        self.min_samples = min_samples
        self.clamp = clamp
        self._samples: int = 0
        self._baseline: float | None = None

        detector_cls = self.DETECTOR_CLASSES.get(detector, drift.ADWIN)
        if detector == "adwin":
            self._detector = detector_cls(delta=delta)
        elif detector == "pagehinkley":
            self._detector = detector_cls(min_instances=min_samples)
        else:
            self._detector = detector_cls()

    def update(
        self,
        value: float,
        current_threshold: float | None = None,
    ) -> DriftResult:
        """Feed a new value and return drift status plus stats."""
        try:
            self._detector.update(value)
        except Exception as e:
            logger.debug(f"Drift detector update failed for {self.metric_key}: {e}")
            return DriftResult()

        self._samples += 1
        estimation = getattr(self._detector, "estimation", None)
        variance = getattr(self._detector, "variance", None)
        width = getattr(self._detector, "width", None)

        if self._baseline is None and estimation is not None:
            self._baseline = float(estimation)

        result = DriftResult(
            estimation=estimation,
            variance=variance,
            width=width,
            old_threshold=current_threshold,
        )

        if self._samples < self.min_samples:
            return result

        if self._detector.drift_detected:
            result.drift_detected = True
            if current_threshold is not None and estimation is not None:
                offset = float(estimation) - (self._baseline or float(estimation))
                offset = max(self.clamp[0], min(self.clamp[1], offset))
                result.proposed_threshold = current_threshold + offset
            logger.info(
                f"Drift detected for {self.metric_key}: "
                f"estimation={estimation} baseline={self._baseline} proposed={result.proposed_threshold}"
            )
            # Reset baseline so subsequent drift is relative to the new regime.
            self._baseline = float(estimation) if estimation is not None else None

        return result

    def get_state(self) -> dict[str, Any]:
        """Return serializable state for debugging/observability."""
        return {
            "metric_key": self.metric_key,
            "detector": self.detector_name,
            "samples": self._samples,
            "baseline": self._baseline,
            "estimation": getattr(self._detector, "estimation", None),
            "variance": getattr(self._detector, "variance", None),
            "width": getattr(self._detector, "width", None),
        }

    def reset(self) -> None:
        """Reset detector and baseline."""
        detector_cls = self.DETECTOR_CLASSES.get(self.detector_name, drift.ADWIN)
        if self.detector_name == "adwin":
            self._detector = detector_cls(delta=self._detector.delta)
        else:
            self._detector = detector_cls()
        self._samples = 0
        self._baseline = None
