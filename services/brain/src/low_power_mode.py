"""
Low-power mode manager for HEMS Brain.

Reduces cognitive loop frequency and LLM API usage when events are predicted to be
minimal — primarily during confirmed sleep or extended absence from home.

Modes:
  normal  — 30s cycle, full LLM + rules
  sleep   — 5min cycle (configurable), rule-triggered LLM escalation
  away    — 10min cycle (configurable), rule-triggered LLM escalation

LLM escalation policy in low-power mode:
  - Critical rules  → execute immediately, no LLM needed
  - Normal rules    → if anything fires AND LLM budget allows, escalate to LLM
                      (LLM gets full context + reason it was woken up)
                      if LLM is on cooldown, execute rule actions directly as fallback
  - Nothing fires   → skip LLM entirely (maximum power saving)

LLM call throttling:
  HEMS_LOW_POWER_LLM_COOLDOWN (default 1800s = 30min) prevents LLM from being
  called more than once per cooldown period in low-power mode, even if rules fire
  repeatedly.

Transitions:
  normal → sleep : biometric sleep stage detected, OR late-night static posture > 10min
  normal → away  : all zones empty for AWAY_CONFIRM_SECONDS (default 5min)
  sleep  → normal: biometric stage = "awake", OR morning activity detected (5-10h)
  away   → normal: any zone occupancy count > 0, OR fresh biometric reading
"""
import os
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Cycle intervals in seconds (configurable via env vars)
LOW_POWER_SLEEP_INTERVAL = int(os.getenv("HEMS_LOW_POWER_SLEEP_INTERVAL", "300"))   # 5 min
LOW_POWER_AWAY_INTERVAL = int(os.getenv("HEMS_LOW_POWER_AWAY_INTERVAL", "600"))     # 10 min
# Minimum seconds between cognitive cycles in low-power mode
LOW_POWER_SLEEP_MIN_INTERVAL = int(os.getenv("HEMS_LOW_POWER_SLEEP_MIN_INTERVAL", "60"))   # 1 min
LOW_POWER_AWAY_MIN_INTERVAL = int(os.getenv("HEMS_LOW_POWER_AWAY_MIN_INTERVAL", "120"))    # 2 min
# Minimum seconds between LLM calls in low-power mode (throttle to avoid frequent API calls)
LOW_POWER_LLM_COOLDOWN = int(os.getenv("HEMS_LOW_POWER_LLM_COOLDOWN", "1800"))      # 30 min
# How long all zones must be continuously empty before entering away mode
AWAY_CONFIRM_SECONDS = int(os.getenv("HEMS_LOW_POWER_AWAY_CONFIRM", "300"))         # 5 min


class PowerMode:
    NORMAL = "normal"
    SLEEP = "sleep"
    AWAY = "away"


class PowerModeManager:
    """Tracks and transitions the system power mode based on world state.

    Instantiate once in Brain.__init__ and call evaluate() at the start of each
    cognitive cycle to keep the mode up to date.

    LLM call policy (low-power mode only):
      allow_llm_call()  — True if enough time has passed since last LLM call
      record_llm_call() — update timestamp after deciding to call LLM
    """

    def __init__(self):
        self._mode: str = PowerMode.NORMAL
        self._reason: str = ""
        self._entered_at: float = 0.0
        # Tracks when we first noticed all zones empty (for away confirmation)
        self._away_candidate_since: float | None = None
        # LLM call throttling in low-power mode
        self._last_llm_call: float = 0.0

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_low_power(self) -> bool:
        return self._mode != PowerMode.NORMAL

    @property
    def cycle_interval(self) -> int:
        """Maximum seconds to wait for an MQTT event before forcing a cycle."""
        if self._mode == PowerMode.SLEEP:
            return LOW_POWER_SLEEP_INTERVAL
        if self._mode == PowerMode.AWAY:
            return LOW_POWER_AWAY_INTERVAL
        return 30  # matches CYCLE_INTERVAL in main.py

    @property
    def min_cycle_interval(self) -> int:
        """Minimum seconds between successive cognitive cycles."""
        if self._mode == PowerMode.SLEEP:
            return LOW_POWER_SLEEP_MIN_INTERVAL
        if self._mode == PowerMode.AWAY:
            return LOW_POWER_AWAY_MIN_INTERVAL
        return 25  # matches MIN_CYCLE_INTERVAL in main.py

    # ------------------------------------------------------------------
    # LLM call throttling
    # ------------------------------------------------------------------

    def allow_llm_call(self, now: float | None = None) -> bool:
        """Return True if an LLM call is permitted under the current rate limit.

        In normal mode this always returns True.
        In low-power mode the call is allowed only if at least
        LOW_POWER_LLM_COOLDOWN seconds have elapsed since the last call.
        """
        if not self.is_low_power:
            return True
        return (now or time.time()) - self._last_llm_call >= LOW_POWER_LLM_COOLDOWN

    def record_llm_call(self, now: float | None = None):
        """Record that an LLM call is being made now (call before dispatching)."""
        self._last_llm_call = now or time.time()

    def seconds_until_llm_allowed(self, now: float | None = None) -> int:
        """Return seconds remaining until next LLM call is allowed (0 if now)."""
        remaining = LOW_POWER_LLM_COOLDOWN - ((now or time.time()) - self._last_llm_call)
        return max(0, int(remaining))

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    def evaluate(self, world_model) -> bool:
        """Check world state and transition power mode if needed.

        Should be called at the start of each cognitive cycle.
        Returns True if the mode changed this call.
        """
        now = time.time()
        bio = world_model.biometric_state
        hour = datetime.now().hour

        # --- Exit conditions (checked before entry to allow fast recovery) ---
        if self._mode == PowerMode.SLEEP:
            # Biometric: sleep stage explicitly returned to awake
            if bio.sleep.stage == "awake" and bio.sleep.last_update > 0:
                return self._transition(PowerMode.NORMAL, "睡眠終了（生体センサー）", now)
            # Activity: morning activity detected (5-10h)
            if 5 <= hour < 10:
                for zone in world_model.zones.values():
                    occ = zone.occupancy
                    if (occ.count > 0
                            and occ.activity_class not in ("idle", "unknown")
                            and occ.last_update > 0):
                        return self._transition(PowerMode.NORMAL, "起床検出（活動開始）", now)
            return False

        if self._mode == PowerMode.AWAY:
            # Camera/perception: someone appeared in any zone
            for zone in world_model.zones.values():
                if zone.occupancy.count > 0:
                    return self._transition(PowerMode.NORMAL, "帰宅検出（在宅確認）", now)
            # Fresh biometric reading means the wearable device is back home
            if (bio.heart_rate.bpm is not None
                    and bio.heart_rate.last_update > now - 120):
                return self._transition(PowerMode.NORMAL, "帰宅検出（バイオメトリクス）", now)
            return False

        # --- Entry conditions (NORMAL mode only) ---

        # Priority 1: Biometric sleep stage (most reliable — from smartband)
        if (bio.sleep.stage in ("deep", "light", "rem")
                and bio.sleep.last_update > 0):
            self._away_candidate_since = None
            return self._transition(
                PowerMode.SLEEP, f"睡眠検出（バイオメトリクス: {bio.sleep.stage}）", now
            )

        # Priority 2: Posture-based sleep (23:00-5:00, idle + static posture > 10min)
        if hour >= 23 or hour < 5:
            for zone in world_model.zones.values():
                occ = zone.occupancy
                if (occ.count > 0
                        and occ.activity_class == "idle"
                        and occ.posture_status == "static"
                        and occ.posture_duration_sec > 600):
                    self._away_candidate_since = None
                    return self._transition(
                        PowerMode.SLEEP, "睡眠検出（姿勢・時間帯）", now
                    )

        # Priority 3: Away detection — all known zones empty for confirmation period
        if world_model.zones:
            all_empty = all(
                z.occupancy.count == 0 for z in world_model.zones.values()
            )
            # Only act when we have fresh occupancy data (sensors are actually reporting)
            any_fresh = any(
                z.occupancy.last_update > 0 for z in world_model.zones.values()
            )
            if all_empty and any_fresh:
                if self._away_candidate_since is None:
                    self._away_candidate_since = now
                    logger.debug(
                        "[低消費電力] 全ゾーン無人を検出 — %d秒後に外出モードへ移行",
                        AWAY_CONFIRM_SECONDS,
                    )
                elif now - self._away_candidate_since >= AWAY_CONFIRM_SECONDS:
                    return self._transition(PowerMode.AWAY, "外出検出（全ゾーン無人）", now)
            else:
                if self._away_candidate_since is not None:
                    logger.debug("[低消費電力] 在宅確認 — 外出モード移行キャンセル")
                self._away_candidate_since = None

        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _transition(self, new_mode: str, reason: str, now: float) -> bool:
        if new_mode == self._mode:
            return False
        logger.info(
            "[低消費電力] モード変更: %s → %s (%s)",
            self._mode, new_mode, reason,
        )
        self._mode = new_mode
        self._reason = reason
        self._entered_at = now
        if new_mode == PowerMode.NORMAL:
            self._away_candidate_since = None
        return True

    def get_status(self) -> dict:
        """Return current power mode status (for logging/dashboard)."""
        return {
            "mode": self._mode,
            "reason": self._reason,
            "entered_at": self._entered_at,
            "cycle_interval_sec": self.cycle_interval,
            "llm_cooldown_remaining_sec": self.seconds_until_llm_allowed(),
        }
