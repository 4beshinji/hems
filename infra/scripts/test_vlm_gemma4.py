#!/usr/bin/env python3
"""
Test gemma4:e4b vision capability against the prompts that
services/perception/src/vlm_analyzer.py actually uses.

Strategy A verification: can the chat-brain model double as a perception VLM?
"""
import argparse
import base64
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

PROMPTS = {
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


def _synthesize_test_image(width: int = 512, height: int = 384) -> bytes:
    """Build a deterministic mock room scene with cv2 shapes that any VLM
    should be able to describe. Returns JPEG bytes."""
    import cv2
    import numpy as np

    img = np.full((height, width, 3), 220, dtype=np.uint8)  # off-white wall

    # Floor (lower 1/3, light wood color)
    cv2.rectangle(img, (0, int(height * 0.66)), (width, height), (140, 170, 200), -1)

    # "Window" upper-left
    cv2.rectangle(img, (40, 40), (180, 180), (200, 230, 250), -1)
    cv2.rectangle(img, (40, 40), (180, 180), (60, 60, 60), 4)
    cv2.line(img, (110, 40), (110, 180), (60, 60, 60), 2)
    cv2.line(img, (40, 110), (180, 110), (60, 60, 60), 2)

    # "Sofa" — bottom-center, blue
    cv2.rectangle(img, (180, 220), (400, 320), (170, 100, 50), -1)
    cv2.rectangle(img, (180, 200), (400, 230), (180, 110, 60), -1)

    # "Desk" — bottom-right, brown
    cv2.rectangle(img, (420, 240), (500, 320), (60, 80, 110), -1)

    # "Person" stick figure on sofa
    cv2.circle(img, (240, 200), 18, (200, 180, 160), -1)  # head
    cv2.rectangle(img, (225, 218), (255, 270), (80, 80, 200), -1)  # torso

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


def _load_image(path: str | None) -> bytes:
    if not path:
        return _synthesize_test_image()
    p = Path(path)
    if not p.exists():
        sys.exit(f"image not found: {path}")
    return p.read_bytes()


def _call_ollama(api: str, model: str, prompt: str, image_b64: str, num_ctx: int) -> tuple[str, float]:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "stream": False,
        # Gemma 4 has a `thinking` capability that, left enabled, consumes the
        # entire num_predict budget on internal reasoning and returns
        # content="". Disable it for scene-description workloads.
        "think": False,
        "options": {"num_ctx": num_ctx, "num_predict": 256},
    }).encode()
    req = urllib.request.Request(
        f"{api}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    elapsed = time.time() - t0
    return data.get("message", {}).get("content", ""), elapsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:11444")
    ap.add_argument("--model", default="gemma4:e4b-it-q8_0")
    ap.add_argument("--image", default=None, help="Path to a real test image (JPEG/PNG). If omitted, a synthetic room is used.")
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--save-image", default=None, help="Write the test image to this path (useful for the synthetic case)")
    args = ap.parse_args()

    img = _load_image(args.image)
    if args.save_image:
        Path(args.save_image).write_bytes(img)
        print(f"Saved test image → {args.save_image}\n")
    image_b64 = base64.b64encode(img).decode()
    print(f"Model: {args.model}")
    print(f"Image: {'synthetic mock room' if not args.image else args.image}  ({len(img)} bytes)")
    print(f"num_ctx: {args.num_ctx}\n")

    for label, prompt in PROMPTS.items():
        print(f"── {label} ──")
        print(f"prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
        try:
            content, elapsed = _call_ollama(args.api, args.model, prompt, image_b64, args.num_ctx)
        except Exception as e:
            print(f"FAIL: {type(e).__name__}: {e}")
            return 1
        print(f"latency: {elapsed:.1f}s")
        print(f"response:\n{content.strip()}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
