"""
Shared utilities for HEMS Brain modules.
"""

import re
from datetime import datetime
from typing import Any

# --------------------------------------------------------------------------- #
#  Voice / TTS constants                                                       #
# --------------------------------------------------------------------------- #

SPEAK_CHUNK_LIMIT = 70  # max chars per speak tool call


# --------------------------------------------------------------------------- #
#  Text splitting                                                              #
# --------------------------------------------------------------------------- #


def split_for_speak(text: str, limit: int = SPEAK_CHUNK_LIMIT) -> list[str]:
    """Split text into chunks of at most *limit* characters, breaking at 。."""
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    sentences = re.split(r"(?<=。)", text)
    chunks: list[str] = []
    buf = ""
    for s in sentences:
        if not s:
            continue
        if len(buf) + len(s) <= limit:
            buf += s
        else:
            if buf:
                chunks.append(buf)
            if len(s) > limit:
                while s:
                    chunks.append(s[:limit])
                    s = s[limit:]
                buf = ""
            else:
                buf = s
    if buf:
        chunks.append(buf)
    return chunks


# --------------------------------------------------------------------------- #
#  Timestamp parsing                                                           #
# --------------------------------------------------------------------------- #


def parse_iso_ts(value: Any) -> float | None:
    """Parse an ISO8601 string (or numeric epoch) to epoch seconds.

    Accepts:
    - ISO8601 strings, including trailing "Z" (e.g. "2026-04-30T12:34:56Z")
    - Numeric epoch (seconds or milliseconds)
    Returns None if the input is not parseable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Heuristic: > 1e11 means milliseconds, else seconds
        return float(value) / 1000 if value > 1e11 else float(value)
    if not isinstance(value, str):
        return None
    try:
        s = value.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return None
