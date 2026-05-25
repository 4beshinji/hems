#!/usr/bin/env python3
"""
Probe Ollama for the largest num_ctx that fits in VRAM with a safety margin.

Reads LLM_MODEL + LLM_API_URL from env (or .env), then loads the model with
progressively larger contexts until total VRAM use exceeds the configured
ceiling. Prints a recommended LLM_NUM_CTX value.

Usage:
    python infra/scripts/recommend_num_ctx.py
    python infra/scripts/recommend_num_ctx.py --apply       # write to .env
    python infra/scripts/recommend_num_ctx.py --margin-mb 2048
    python infra/scripts/recommend_num_ctx.py --max 131072
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# Candidate context sizes — biased toward common power-of-two boundaries plus
# a few intermediate steps so we don't over-allocate when the next step is far.
CANDIDATES = [4096, 8192, 16384, 24576, 32768, 49152, 65536, 98304, 131072]


def _read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.split("#", 1)[0].strip()
    return out


def _detect_total_vram_mb() -> int | None:
    """Return total GPU VRAM in MB (NVIDIA or AMD)."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip().splitlines()[0])
    except FileNotFoundError:
        pass
    try:
        r = subprocess.run(["rocm-smi", "--showmeminfo", "vram"],
                           capture_output=True, text=True, timeout=5)
        m = re.search(r"VRAM Total Memory \(B\):\s*(\d+)", r.stdout)
        if m:
            return int(m.group(1)) // (1024 * 1024)
    except FileNotFoundError:
        pass
    return None


def _detect_used_vram_mb() -> int | None:
    """Return current GPU VRAM in use across the device (any process)."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip().splitlines()[0])
    except FileNotFoundError:
        pass
    try:
        r = subprocess.run(["rocm-smi", "--showmeminfo", "vram"],
                           capture_output=True, text=True, timeout=5)
        m = re.search(r"VRAM Total Used Memory \(B\):\s*(\d+)", r.stdout)
        if m:
            return int(m.group(1)) // (1024 * 1024)
    except FileNotFoundError:
        pass
    return None


def _ollama_probe(api: str, model: str, num_ctx: int, timeout: int) -> bool:
    """Load `model` with given num_ctx by issuing a tiny generate. True if 200."""
    body = json.dumps({
        "model": model,
        "prompt": "hi",
        "stream": False,
        "options": {"num_ctx": num_ctx},
    }).encode()
    req = urllib.request.Request(
        f"{api}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def _resolve_api(env: dict) -> str:
    api = env.get("LLM_API_URL", "http://localhost:11444/v1")
    # The native API lives at the same host without /v1.
    api = api.rstrip("/").removesuffix("/v1")
    api = api.replace("ollama:11434", "localhost:11444")  # in-container hostname → host port
    return api


def _update_env_num_ctx(value: int) -> None:
    text = ENV_PATH.read_text() if ENV_PATH.exists() else ""
    line = f"LLM_NUM_CTX={value}  # auto-tuned by recommend_num_ctx.py\n"
    if re.search(r"^\s*#?\s*LLM_NUM_CTX=", text, re.MULTILINE):
        new = re.sub(r"^\s*#?\s*LLM_NUM_CTX=.*$", line.rstrip(), text, flags=re.MULTILINE)
    else:
        new = text + ("\n" if text and not text.endswith("\n") else "") + line
    ENV_PATH.write_text(new)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--margin-mb", type=int, default=1024,
                   help="Reserve this much VRAM for other GPU users (default: 1024)")
    p.add_argument("--max", type=int, default=131072,
                   help="Upper bound on num_ctx to probe (default: 131072)")
    p.add_argument("--model", default=None, help="Override LLM_MODEL")
    p.add_argument("--api", default=None, help="Override LLM_API_URL (native, no /v1)")
    p.add_argument("--apply", action="store_true",
                   help="Write LLM_NUM_CTX to .env when done")
    args = p.parse_args()

    env = _read_env(ENV_PATH)
    model = args.model or env.get("LLM_MODEL")
    if not model:
        print("ERROR: LLM_MODEL not set (in .env or via --model)", file=sys.stderr)
        return 2
    api = args.api or _resolve_api(env)

    total = _detect_total_vram_mb()
    if not total:
        print("ERROR: could not detect VRAM (need nvidia-smi or rocm-smi)", file=sys.stderr)
        return 2
    ceiling = total - args.margin_mb
    print(f"GPU VRAM: {total} MB total, ceiling = {ceiling} MB ({args.margin_mb} MB margin)")
    print(f"Model:    {model}")
    print(f"API:      {api}")
    print()

    candidates = [c for c in CANDIDATES if c <= args.max]
    best = None
    for ctx in candidates:
        ok = _ollama_probe(api, model, ctx, timeout=240)
        # Give the runtime a beat to settle KV allocation in `ollama ps`.
        time.sleep(2)
        used = _detect_used_vram_mb()
        if not ok:
            print(f"  num_ctx={ctx:>6}  load=FAIL")
            break
        if used is None:
            print(f"  num_ctx={ctx:>6}  load=OK   used=? (no telemetry)")
            best = ctx
            continue
        status = "OK" if used <= ceiling else "OVER CEILING"
        print(f"  num_ctx={ctx:>6}  load=OK   used={used} MB  ({status})")
        if used > ceiling:
            break
        best = ctx

    print()
    if best is None:
        print("FAIL: even the smallest candidate did not fit. Lower --margin-mb?")
        return 1
    print(f"Recommended LLM_NUM_CTX={best}")
    if args.apply:
        _update_env_num_ctx(best)
        print(f"Wrote LLM_NUM_CTX={best} to {ENV_PATH}")
        print("Restart brain to take effect:  cd infra && docker compose up -d brain")
    else:
        print("(re-run with --apply to write to .env)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
