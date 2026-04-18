"""
VLM (Vision Language Model) Analyzer — Ollama vision API client with dual-model support.

Encodes camera frames to base64 JPEG (RAM only), calls Ollama chat API with images.
Supports light tier (moondream, coexists with brain LLM) and heavy tier
(minicpm-v, evicts brain LLM from VRAM).
"""

import base64
import time

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
    """Ollama vision API client with dual-model (light/heavy) support."""

    def __init__(
        self,
        ollama_url: str = "http://ollama:11434",
        light_model: str = "moondream",
        heavy_model: str = "minicpm-v",
        timeout: int = 30,
        max_tokens: int = 256,
        max_image_size: int = 512,
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.light_model = light_model
        self.heavy_model = heavy_model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.max_image_size = max_image_size

        # Model availability cache: {model_name: (available, checked_at)}
        self._model_cache: dict[str, tuple[bool, float]] = {}
        self._model_cache_ttl = 120  # 2 minutes

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

    async def _check_model_available(self, model: str, session: aiohttp.ClientSession) -> bool:
        """Check if a model is available in Ollama. Caches for 2 minutes."""
        cached = self._model_cache.get(model)
        if cached and time.time() - cached[1] < self._model_cache_ttl:
            return cached[0]

        try:
            async with session.get(
                f"{self.ollama_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    # Match both exact name and name:latest
                    available = any(model == m or model == m.split(":")[0] for m in models)
                    self._model_cache[model] = (available, time.time())
                    return available
        except Exception as e:
            logger.debug(f"VLM model check failed: {e}")

        self._model_cache[model] = (False, time.time())
        return False

    async def _unload_model(self, model: str, session: aiohttp.ClientSession) -> None:
        """Unload model from VRAM via keep_alive=0."""
        try:
            async with session.post(
                f"{self.ollama_url}/api/generate",
                json={"model": model, "keep_alive": "0"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    logger.debug(f"VLM model unloaded: {model}")
                else:
                    logger.warning(f"VLM model unload failed: {model} HTTP {resp.status}")
        except Exception as e:
            logger.warning(f"VLM model unload error ({model}): {e}")

    async def analyze(
        self,
        frame: np.ndarray,
        session: aiohttp.ClientSession,
        prompt: str | None = None,
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
            tier: "light" (moondream) or "heavy" (minicpm-v).
            zone: Zone identifier for result tagging.

        Returns:
            dict with description, objects, scene_type, anomalies, model, tier,
            elapsed_ms, timestamp, zone.
        """
        model = self.heavy_model if tier == "heavy" else self.light_model
        text_prompt = prompt or _PROMPTS.get(mode, _PROMPTS["general"])

        # Encode frame
        image_b64 = self._encode_frame(frame)

        start = time.time()
        try:
            async with session.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": text_prompt,
                            "images": [image_b64],
                        }
                    ],
                    "stream": False,
                    "options": {
                        "num_predict": self.max_tokens,
                    },
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
                content = data.get("message", {}).get("content", "")

                # Parse response into structured fields
                result = self._parse_response(content, mode)
                result.update(
                    {
                        "model": model,
                        "tier": tier,
                        "mode": mode,
                        "elapsed_ms": elapsed_ms,
                        "timestamp": time.time(),
                        "zone": zone,
                    }
                )
                return result

        except TimeoutError:
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
        # Common room objects to look for
        _object_keywords = [
            "chair",
            "desk",
            "table",
            "sofa",
            "couch",
            "bed",
            "lamp",
            "monitor",
            "computer",
            "keyboard",
            "phone",
            "book",
            "cup",
            "bottle",
            "plant",
            "window",
            "door",
            "shelf",
            "cabinet",
            "tv",
            "television",
            "fan",
            "air conditioner",
            "person",
            "cat",
            "dog",
        ]
        lower = description.lower()
        for obj in _object_keywords:
            if obj in lower:
                objects.append(obj)

        # Classify scene type
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

        # Detect anomalies (safety mode especially)
        anomalies: list[str] = []
        _anomaly_keywords = [
            "fire",
            "smoke",
            "water",
            "flood",
            "fallen",
            "hazard",
            "danger",
            "broken",
            "damage",
            "leak",
            "spill",
            "unusual",
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


# Needed for TimeoutError in async context
