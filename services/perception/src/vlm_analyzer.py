"""
VLM (Vision Language Model) analyzer — OpenAI-compatible vision client.

Encodes camera frames to base64 JPEG in RAM, then calls `/v1/chat/completions`
on a llama.cpp `--mmproj` server (default: `vlm-light` + `vlm-heavy`). Light and
heavy tiers point at separate base URLs so both models can stay resident with no
swap step. Ollama's OpenAI-compat endpoint works too when legacy fallback is
configured.
"""
import asyncio
import base64
import time
from typing import Optional

import aiohttp
import cv2
import numpy as np
from loguru import logger

# Prompt templates for different analysis modes
_PROMPTS = {
    "general": (
        "Describe this room scene briefly. "
        "List visible objects, people count, and overall room state. "
        "Keep it under 3 sentences."
    ),
    "safety": (
        "Check this room for any safety hazards or anomalies. "
        "Look for: fire/smoke, water on floor, fallen person, open windows/doors that shouldn't be, "
        "unusual objects, or anything dangerous. Report only actual concerns, or say 'no issues'."
    ),
    "environment": (
        "Describe the room environment state: lighting level (bright/dim/dark), "
        "tidiness (clean/messy), and any notable changes or items out of place. "
        "Keep it under 3 sentences."
    ),
}


class VLMAnalyzer:
    """OpenAI-compatible vision client with light/heavy tier support."""

    def __init__(
        self,
        light_url: str = "http://vlm-light:8080/v1",
        heavy_url: str = "http://vlm-heavy:8080/v1",
        light_model: str = "minicpm-v",
        heavy_model: str = "qwen2-vl-7b",
        timeout: int = 30,
        max_tokens: int = 256,
        max_image_size: int = 512,
    ):
        self.light_url = self._normalize_base(light_url)
        self.heavy_url = self._normalize_base(heavy_url)
        self.light_model = light_model
        self.heavy_model = heavy_model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.max_image_size = max_image_size

        # Model availability cache: {tier: (available, checked_at)}
        self._model_cache: dict[str, tuple[bool, float]] = {}
        self._model_cache_ttl = 120  # 2 minutes

    @staticmethod
    def _normalize_base(url: str) -> str:
        base = url.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        return base

    def _tier_url(self, tier: str) -> str:
        return self.heavy_url if tier == "heavy" else self.light_url

    def _tier_model(self, tier: str) -> str:
        return self.heavy_model if tier == "heavy" else self.light_model

    def _encode_frame(self, frame: np.ndarray) -> str:
        """Resize frame to max dimension and encode as base64 JPEG."""
        h, w = frame.shape[:2]
        max_dim = self.max_image_size
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return base64.b64encode(buf.tobytes()).decode("ascii")

    async def _check_tier_available(
        self, tier: str, session: aiohttp.ClientSession
    ) -> bool:
        """Check if the tier's server responds on `/v1/models`. Cached 2 min."""
        cached = self._model_cache.get(tier)
        if cached and time.time() - cached[1] < self._model_cache_ttl:
            return cached[0]

        url = self._tier_url(tier)
        try:
            async with session.get(
                f"{url}/models",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                available = resp.status == 200
                self._model_cache[tier] = (available, time.time())
                return available
        except Exception as e:
            logger.debug(f"VLM tier {tier} availability check failed: {e}")

        self._model_cache[tier] = (False, time.time())
        return False

    async def analyze(
        self,
        frame: np.ndarray,
        session: aiohttp.ClientSession,
        prompt: Optional[str] = None,
        mode: str = "general",
        tier: str = "light",
        zone: str = "",
    ) -> dict:
        """Analyze a camera frame using VLM.

        Args:
            frame: OpenCV BGR frame (numpy array).
            session: aiohttp client session.
            prompt: Custom prompt (overrides mode template).
            mode: Prompt mode — "general", "safety", or "environment".
            tier: "light" (small model) or "heavy" (larger model).
            zone: Zone identifier for result tagging.

        Returns:
            dict with description, objects, scene_type, anomalies, model, tier,
            elapsed_ms, timestamp, zone.
        """
        url = self._tier_url(tier)
        model = self._tier_model(tier)
        text_prompt = prompt or _PROMPTS.get(mode, _PROMPTS["general"])

        image_b64 = self._encode_frame(frame)
        data_url = f"data:image/jpeg;base64,{image_b64}"

        start = time.time()
        try:
            async with session.post(
                f"{url}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": text_prompt},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        }
                    ],
                    "stream": False,
                    "max_tokens": self.max_tokens,
                },
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                elapsed_ms = int((time.time() - start) * 1000)
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.warning(f"VLM API error: HTTP {resp.status} — {error_text[:200]}")
                    return {
                        "error": f"HTTP {resp.status}",
                        "model": model,
                        "tier": tier,
                        "elapsed_ms": elapsed_ms,
                        "timestamp": time.time(),
                        "zone": zone,
                    }

                data = await resp.json()
                choices = data.get("choices") or []
                content = ""
                if choices:
                    content = (choices[0].get("message") or {}).get("content", "") or ""

                result = self._parse_response(content, mode)
                result.update({
                    "model": model,
                    "tier": tier,
                    "mode": mode,
                    "elapsed_ms": elapsed_ms,
                    "timestamp": time.time(),
                    "zone": zone,
                })
                return result

        except asyncio.TimeoutError:
            elapsed_ms = int((time.time() - start) * 1000)
            logger.warning(f"VLM timeout after {elapsed_ms}ms (model={model})")
            return {
                "error": "timeout",
                "model": model,
                "tier": tier,
                "elapsed_ms": elapsed_ms,
                "timestamp": time.time(),
                "zone": zone,
            }
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            logger.error(f"VLM analysis error: {e}")
            return {
                "error": str(e),
                "model": model,
                "tier": tier,
                "elapsed_ms": elapsed_ms,
                "timestamp": time.time(),
                "zone": zone,
            }

    def _parse_response(self, content: str, mode: str) -> dict:
        """Parse VLM text response into structured fields."""
        description = content.strip()

        # Extract objects mentioned (simple keyword extraction)
        objects: list[str] = []
        _object_keywords = [
            "chair", "desk", "table", "sofa", "couch", "bed", "lamp", "monitor",
            "computer", "keyboard", "phone", "book", "cup", "bottle", "plant",
            "window", "door", "shelf", "cabinet", "tv", "television", "fan",
            "air conditioner", "person", "cat", "dog",
        ]
        lower = description.lower()
        for obj in _object_keywords:
            if obj in lower:
                objects.append(obj)

        scene_type = "unknown"
        if any(w in lower for w in ("bedroom", "bed", "sleeping", "pillow")):
            scene_type = "bedroom"
        elif any(w in lower for w in ("kitchen", "cook", "stove", "fridge")):
            scene_type = "kitchen"
        elif any(w in lower for w in ("living room", "sofa", "couch", "tv")):
            scene_type = "living_room"
        elif any(w in lower for w in ("office", "desk", "computer", "monitor")):
            scene_type = "office"
        elif any(w in lower for w in ("bathroom", "shower", "toilet")):
            scene_type = "bathroom"

        anomalies: list[str] = []
        _anomaly_keywords = [
            "fire", "smoke", "water", "flood", "fallen", "hazard", "danger",
            "broken", "damage", "leak", "spill", "unusual",
        ]
        for kw in _anomaly_keywords:
            if kw in lower and "no " + kw not in lower and "no issues" not in lower:
                anomalies.append(kw)

        return {
            "description": description,
            "objects": objects,
            "scene_type": scene_type,
            "anomalies": anomalies,
        }
