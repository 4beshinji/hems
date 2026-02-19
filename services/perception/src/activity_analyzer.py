"""
ActivityAnalyzer — tiered pose buffer with posture-stasis detection.

Buffer architecture (time-decaying resolution):
  Tier 0 (raw):   last 60s,  every frame          (~20 entries @3s)
  Tier 1 (10s):   last 10m,  1 summary / 10s      (~60 entries)
  Tier 2 (1min):  last 1h,   1 summary / 60s      (~60 entries)
  Tier 3 (5min):  last 4h,   1 summary / 300s     (~48 entries)

Total: ~188 entries max, covering up to 4 hours of history.

Each summary stores a normalised posture signature (hip-centred,
shoulder-width = 1.0) so posture comparisons are position/scale invariant.
"""
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_KPT_CONF_THRESH = 0.3

# COCO keypoint indices
_L_SHOULDER, _R_SHOULDER = 5, 6
_L_HIP, _R_HIP = 11, 12

# Activity classification thresholds (normalised displacement / sec)
_ACTIVITY_THRESHOLDS = {"idle": 0.002, "low": 0.01, "moderate": 0.04}

# Posture similarity: normalised MSE below this ≈ "same posture"
_POSTURE_SAME_THRESH = 0.05

# Posture status thresholds (seconds in same posture)
_POSTURE_STATIC_SEC = 1200    # 20 min → "static"
_POSTURE_MOSTLY_SEC = 600     # 10 min → "mostly_static"

# Tier definitions: (name, max_age_sec, bucket_resolution_sec)
_TIER_DEFS = [
    ("raw",  60,    0),       # Tier 0: keep every frame
    ("10s",  600,   10),      # Tier 1
    ("1min", 3600,  60),      # Tier 2
    ("5min", 14400, 300),     # Tier 3
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class PoseSnapshot:
    """Raw single-frame capture."""
    timestamp: float
    persons: List[Tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    # persons: list of (keypoints (17,2), keypoint_conf (17,))


@dataclass
class PoseSummary:
    """Consolidated entry for higher tiers."""
    timestamp: float                      # bucket midpoint
    person_count: int
    posture_sig: Optional[np.ndarray]     # (17, 2) normalised, or None
    displacement: float                   # mean displacement in bucket


# ---------------------------------------------------------------------------
# Posture normalisation
# ---------------------------------------------------------------------------
def normalise_posture(
    keypoints: np.ndarray,
    confidences: np.ndarray,
) -> Optional[np.ndarray]:
    """
    Normalise a (17, 2) skeleton to be position & scale invariant.

    Anchor = midpoint(left_hip, right_hip)
    Scale  = dist(left_shoulder, right_shoulder)

    Returns (17, 2) normalised keypoints, or None if anchors not visible.
    Low-confidence keypoints are set to (0, 0).
    """
    visible = confidences > _KPT_CONF_THRESH

    # Need at least hips + shoulders for normalisation
    anchors = [_L_SHOULDER, _R_SHOULDER, _L_HIP, _R_HIP]
    if not all(visible[i] for i in anchors):
        return None

    hip_mid = (keypoints[_L_HIP] + keypoints[_R_HIP]) / 2.0
    shoulder_width = np.linalg.norm(
        keypoints[_L_SHOULDER] - keypoints[_R_SHOULDER]
    )
    if shoulder_width < 1e-6:
        return None

    normed = np.zeros_like(keypoints)
    for i in range(17):
        if visible[i]:
            normed[i] = (keypoints[i] - hip_mid) / shoulder_width
        # else stays (0, 0)

    return normed


def posture_distance(a: np.ndarray, b: np.ndarray) -> float:
    """
    MSE between two normalised posture signatures.
    Only compares keypoints that are non-zero in BOTH signatures.
    """
    mask_a = np.any(a != 0, axis=1)
    mask_b = np.any(b != 0, axis=1)
    mask = mask_a & mask_b
    if not np.any(mask):
        return float("inf")
    diff = a[mask] - b[mask]
    return float(np.mean(np.sum(diff ** 2, axis=1)))


# ---------------------------------------------------------------------------
# Main analyser
# ---------------------------------------------------------------------------
class ActivityAnalyzer:
    """
    Tiered pose buffer with short-term activity and long-term stasis analysis.
    """

    def __init__(self, frame_size: Tuple[int, int] = (800, 600)):
        self._diag = float(np.hypot(*frame_size))

        # Tier 0: raw snapshots
        self._raw: Deque[PoseSnapshot] = deque()

        # Tiers 1–3: consolidated summaries
        self._tiers: List[Deque[PoseSummary]] = [deque() for _ in range(3)]

        # Track last consolidation timestamps
        self._last_consolidate = [0.0, 0.0, 0.0]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def push(self, persons: list, timestamp: Optional[float] = None):
        """
        Add a pose estimation result.

        Args:
            persons: list of dicts with 'keypoints' (17,2), 'keypoint_conf' (17,)
        """
        ts = timestamp or time.time()
        snap = PoseSnapshot(
            timestamp=ts,
            persons=[(p["keypoints"], p["keypoint_conf"]) for p in persons],
        )
        self._raw.append(snap)
        self._maybe_consolidate(ts)
        self._evict(ts)

    def analyze(self) -> dict:
        """
        Full analysis across all tiers.

        Returns:
            activity_level:       float 0-1 (short-term movement)
            activity_class:       "idle" | "low" | "moderate" | "high"
            posture_duration_sec: how long current posture has been held
            posture_status:       "changing" | "mostly_static" | "static"
            buffer_depth:         {raw, tier1, tier2, tier3} entry counts
        """
        activity = self._compute_short_term_activity()
        posture = self._compute_posture_stasis()

        return {
            "activity_level": activity["level"],
            "activity_class": activity["class"],
            "posture_duration_sec": posture["duration_sec"],
            "posture_status": posture["status"],
            "buffer_depth": {
                "raw": len(self._raw),
                "tier1": len(self._tiers[0]),
                "tier2": len(self._tiers[1]),
                "tier3": len(self._tiers[2]),
            },
        }

    def clear(self):
        self._raw.clear()
        for t in self._tiers:
            t.clear()

    # ------------------------------------------------------------------
    # Short-term activity (from Tier 0 raw buffer)
    # ------------------------------------------------------------------

    def _compute_short_term_activity(self) -> dict:
        if len(self._raw) < 2:
            return {"level": 0.0, "class": "idle"}

        displacements = []
        items = list(self._raw)
        for i in range(1, len(items)):
            dt = items[i].timestamp - items[i - 1].timestamp
            if dt <= 0:
                continue
            disp = self._snapshot_displacement(items[i - 1], items[i])
            if disp is not None:
                displacements.append((disp / self._diag) / dt)

        level = min(float(np.mean(displacements)), 1.0) if displacements else 0.0
        return {"level": round(level, 4), "class": self._classify_activity(level)}

    # ------------------------------------------------------------------
    # Long-term posture stasis (across ALL tiers)
    # ------------------------------------------------------------------

    def _compute_posture_stasis(self) -> dict:
        """Walk backwards through all tiers to find how long the same posture
        has been held."""
        current_sig = self._current_posture_sig()
        if current_sig is None:
            return {"duration_sec": 0.0, "status": "changing"}

        now = self._raw[-1].timestamp if self._raw else time.time()
        earliest_same = now

        # Walk tiers from finest to coarsest
        all_entries = self._all_entries_reverse()

        for entry_ts, entry_sig in all_entries:
            if entry_sig is None:
                break
            dist = posture_distance(current_sig, entry_sig)
            if dist < _POSTURE_SAME_THRESH:
                earliest_same = entry_ts
            else:
                break

        duration = now - earliest_same
        if duration >= _POSTURE_STATIC_SEC:
            status = "static"
        elif duration >= _POSTURE_MOSTLY_SEC:
            status = "mostly_static"
        else:
            status = "changing"

        return {"duration_sec": round(duration, 1), "status": status}

    def _current_posture_sig(self) -> Optional[np.ndarray]:
        """Get normalised posture signature from the latest raw snapshot."""
        if not self._raw:
            return None
        snap = self._raw[-1]
        if not snap.persons:
            return None
        kp, conf = snap.persons[0]
        return normalise_posture(kp, conf)

    def _all_entries_reverse(self):
        """
        Yield (timestamp, posture_sig) from all tiers, newest first.
        Raw snapshots are converted to signatures on the fly.
        """
        # Tier 0 (raw) — newest first
        for snap in reversed(self._raw):
            if snap.persons:
                kp, conf = snap.persons[0]
                sig = normalise_posture(kp, conf)
                yield snap.timestamp, sig
            else:
                yield snap.timestamp, None

        # Tiers 1-3 — newest first
        for tier in self._tiers:
            for entry in reversed(tier):
                yield entry.timestamp, entry.posture_sig

    # ------------------------------------------------------------------
    # Tier consolidation
    # ------------------------------------------------------------------

    def _maybe_consolidate(self, now: float):
        """Consolidate raw → tier1, tier1 → tier2, tier2 → tier3 as needed."""
        # tier_idx 0: raw → tier1  (every 10s)
        # tier_idx 1: tier1 → tier2 (every 60s)
        # tier_idx 2: tier2 → tier3 (every 300s)
        resolutions = [
            _TIER_DEFS[1][2],  # 10s
            _TIER_DEFS[2][2],  # 60s
            _TIER_DEFS[3][2],  # 300s
        ]

        for tier_idx, resolution in enumerate(resolutions):
            if now - self._last_consolidate[tier_idx] < resolution:
                continue
            self._last_consolidate[tier_idx] = now

            if tier_idx == 0:
                summary = self._summarise_raw(now, resolution)
            else:
                summary = self._summarise_tier(tier_idx - 1, now, resolution)

            if summary is not None:
                self._tiers[tier_idx].append(summary)

    def _summarise_raw(self, now: float, window: float) -> Optional[PoseSummary]:
        """Summarise recent raw snapshots into a single PoseSummary."""
        cutoff = now - window
        entries = [s for s in self._raw if s.timestamp >= cutoff]
        if not entries:
            return None

        # Average posture signature
        sigs = []
        for snap in entries:
            if snap.persons:
                kp, conf = snap.persons[0]
                sig = normalise_posture(kp, conf)
                if sig is not None:
                    sigs.append(sig)

        avg_sig = np.mean(sigs, axis=0) if sigs else None

        # Average displacement
        disps = []
        for i in range(1, len(entries)):
            d = self._snapshot_displacement(entries[i - 1], entries[i])
            if d is not None:
                disps.append(d / self._diag)

        person_counts = [len(s.persons) for s in entries if s.persons]
        avg_persons = int(round(np.mean(person_counts))) if person_counts else 0

        return PoseSummary(
            timestamp=entries[len(entries) // 2].timestamp,
            person_count=avg_persons,
            posture_sig=avg_sig,
            displacement=float(np.mean(disps)) if disps else 0.0,
        )

    def _summarise_tier(
        self, source_idx: int, now: float, window: float
    ) -> Optional[PoseSummary]:
        """Summarise entries from a lower tier into the next tier."""
        cutoff = now - window
        source = self._tiers[source_idx]
        entries = [e for e in source if e.timestamp >= cutoff]
        if not entries:
            return None

        sigs = [e.posture_sig for e in entries if e.posture_sig is not None]
        avg_sig = np.mean(sigs, axis=0) if sigs else None

        return PoseSummary(
            timestamp=entries[len(entries) // 2].timestamp,
            person_count=int(round(np.mean([e.person_count for e in entries]))),
            posture_sig=avg_sig,
            displacement=float(np.mean([e.displacement for e in entries])),
        )

    # ------------------------------------------------------------------
    # Eviction
    # ------------------------------------------------------------------

    def _evict(self, now: float):
        """Remove entries older than each tier's max age."""
        max_ages = [td[1] for td in _TIER_DEFS]

        # Tier 0 (raw)
        cutoff = now - max_ages[0]
        while self._raw and self._raw[0].timestamp < cutoff:
            self._raw.popleft()

        # Tiers 1-3
        for i, tier in enumerate(self._tiers):
            cutoff = now - max_ages[i + 1]
            while tier and tier[0].timestamp < cutoff:
                tier.popleft()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _snapshot_displacement(prev: PoseSnapshot, curr: PoseSnapshot) -> Optional[float]:
        """Mean keypoint displacement between two raw snapshots."""
        n = min(len(prev.persons), len(curr.persons))
        if n == 0:
            return None

        total_disp = 0.0
        total_kpts = 0
        for pi in range(n):
            kp_prev, conf_prev = prev.persons[pi]
            kp_curr, conf_curr = curr.persons[pi]
            visible = (conf_prev > _KPT_CONF_THRESH) & (conf_curr > _KPT_CONF_THRESH)
            if not np.any(visible):
                continue
            diff = kp_curr[visible] - kp_prev[visible]
            dists = np.linalg.norm(diff, axis=1)
            total_disp += float(np.sum(dists))
            total_kpts += int(np.sum(visible))

        return total_disp / total_kpts if total_kpts > 0 else None

    @staticmethod
    def _classify_activity(level: float) -> str:
        if level < _ACTIVITY_THRESHOLDS["idle"]:
            return "idle"
        if level < _ACTIVITY_THRESHOLDS["low"]:
            return "low"
        if level < _ACTIVITY_THRESHOLDS["moderate"]:
            return "moderate"
        return "high"
