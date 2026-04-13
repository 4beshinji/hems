"""Static travel time configuration (Phase 1). Phase 3 adds histogram + Maps API."""
import json
import os
from loguru import logger

DEFAULT_TRAVEL_MIN = int(os.getenv("TRAVEL_DEFAULT_MIN", "20"))


def load_travel_matrix() -> dict[tuple[str, str], int]:
    """Load static travel times from env TRAVEL_TIMES_JSON.

    Shape: {"home→office": 25, "office→home": 30, "home→gym": 15}
    Returns: {(origin, dest): minutes}
    """
    raw = os.getenv("TRAVEL_TIMES_JSON", "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse TRAVEL_TIMES_JSON: {e}")
        return {}

    matrix: dict[tuple[str, str], int] = {}
    for key, val in parsed.items():
        if "→" in key:
            origin, dest = key.split("→", 1)
        elif "->" in key:
            origin, dest = key.split("->", 1)
        elif "_to_" in key:
            origin, dest = key.split("_to_", 1)
        else:
            continue
        try:
            matrix[(origin.strip(), dest.strip())] = int(val)
        except (ValueError, TypeError):
            continue
    return matrix


def lookup_travel_minutes(
    matrix: dict[tuple[str, str], int],
    origin: str,
    dest: str,
) -> int:
    """Look up travel time, falling back to DEFAULT_TRAVEL_MIN."""
    key = (origin, dest)
    if key in matrix:
        return matrix[key]
    return DEFAULT_TRAVEL_MIN
