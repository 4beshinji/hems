"""
Type / physical-range validation for inbound MQTT sensor payloads.

Input trust boundary (ported from SOMS Group B, commit 20a76bf): the HEMS
MQTT broker currently runs `allow_anonymous true` (see hardening audit P0-1),
so any LAN publisher can inject crafted sensor values that flow straight into
the LLM context via `WorldModel.update_from_mqtt` and into the event-store
data mart. This module enforces a numeric type check + physical-plausibility
range *before* fusion / persistence, so out-of-range or non-numeric injections
are dropped (and logged by the caller) rather than silently clamped — silent
clamping would hide the injection from operators.

Output-side guards (device allowlist, brightness/pulse bounds, urgency range,
rate limits) live in `sanitizer.py`; this is the missing input-side guard.

Only ANALOG channels (those that feed sensor fusion) are validated; EVENT /
STATE / PASSTHROUGH channels legitimately carry non-numeric payloads
(door="open", presence="on") and are handled by their own update paths.
"""

# Inclusive physical bounds per analog channel. Generous enough to admit any
# plausible real reading, tight enough to reject obvious injections / garbage.
# Keys must stay aligned with the ANALOG entries in
# `sensor_fusion.CHANNEL_REGISTRY`.
NUMERIC_RANGES = {
    "temperature": (-40.0, 60.0),  # °C — ambient air
    "humidity": (0.0, 100.0),  # %RH
    "co2": (0.0, 50000.0),  # ppm (NDIR sensors top out well below)
    "pressure": (800.0, 1100.0),  # hPa — sea-level atmospheric range
    "illuminance": (0.0, 200000.0),  # lux — direct sunlight ≈ 100k
    "light": (0.0, 200000.0),  # lux (hems alias of illuminance)
    "soil_moisture": (0.0, 100.0),  # %
    "voc": (0.0, 10_000_000.0),  # BME680 VOC (index/ppb/Ω — units vary)
    "pm25": (0.0, 100000.0),  # µg/m³ — generous upper bound
}


def _coerce_number(value) -> float | None:
    """Coerce a value to float, accepting bool/int/float/numeric-string.

    Returns None for anything non-numeric (plain strings, lists, dicts,
    None). bool is intentionally accepted (True/False -> 1.0/0.0) because
    edge devices publish JSON booleans for state channels.
    """
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except (ValueError, AttributeError):
            return None
    return None


def validate_sensor_value(channel: str, value) -> tuple[bool, float | None]:
    """Validate an inbound analog sensor value for a channel.

    Args:
        channel: channel name (e.g. "temperature", "co2", "light").
        value: raw value from the MQTT payload.

    Returns:
        (ok, coerced):
          - (True, float) when the value is numeric and (for channels with a
            defined physical range) within range.
          - (False, None) when the value is non-numeric, NaN/±inf, or out of
            range for a channel with a defined physical range.

    Channels without a defined range only have to be numeric-coercible; this
    drops non-numeric injections while admitting unfamiliar analog readings.
    """
    coerced = _coerce_number(value)
    if coerced is None:
        return False, None
    if coerced != coerced or coerced in (float("inf"), float("-inf")):
        # NaN / ±inf — float("nan") and float("inf") parse but are never valid.
        return False, None

    bounds = NUMERIC_RANGES.get(channel)
    if bounds is not None:
        lo, hi = bounds
        if not (lo <= coerced <= hi):
            return False, None

    return True, coerced
