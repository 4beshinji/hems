"""WorldModel-wide non-alert time-window constants.

These values are freshness windows, not alert thresholds, so they live outside
rules.config.RuleThresholds per the W2.1 design note.
"""

import os

# A reading older than ENV_STALE_SEC is annotated as stale in the LLM context.
ENV_STALE_SEC = int(os.getenv("HEMS_ENV_STALE_SEC", "300"))  # 5 min

# A zone with no update for ZONE_BLIND_SEC counts toward system-wide blindness,
# which puts the cognitive loop into observe-only mode (side-effects suppressed).
ZONE_BLIND_SEC = int(os.getenv("HEMS_ZONE_BLIND_SEC", "300"))  # 5 min
