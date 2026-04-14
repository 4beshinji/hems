"""
Shared utilities for HEMS Brain modules.
"""
import os
import re

# --------------------------------------------------------------------------- #
#  Auth                                                                        #
# --------------------------------------------------------------------------- #

_HEMS_API_KEY = os.getenv("HEMS_API_KEY", "")
AUTH_HEADERS: dict[str, str] = (
    {"Authorization": f"Bearer {_HEMS_API_KEY}"} if _HEMS_API_KEY else {}
)

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
