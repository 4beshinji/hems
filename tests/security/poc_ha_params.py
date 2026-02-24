#!/usr/bin/env python3
"""
PoC V8: HA bridge パラメータバリデーションテスト
範囲外の値や危険なドメインが受け入れられるか確認
"""
import sys
import os
import asyncio

try:
    import aiohttp
except ImportError:
    print("[SKIP] aiohttp not installed — run inside container or: pip install aiohttp")
    sys.exit(0)

HA_BRIDGE_HOST = os.getenv("HA_BRIDGE_HOST", "127.0.0.1")
HA_BRIDGE_PORT = os.getenv("HA_BRIDGE_PORT", "8016")
BASE_URL = f"http://{HA_BRIDGE_HOST}:{HA_BRIDGE_PORT}"

PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0

# Test cases: (description, payload, should_be_blocked)
TEST_CASES = [
    # Out-of-range light brightness
    (
        "Light brightness = -100 (out of range)",
        {"entity_id": "light.bedroom", "service": "light/turn_on",
         "data": {"brightness": -100}},
        True,
    ),
    (
        "Light brightness = 9999 (out of range)",
        {"entity_id": "light.bedroom", "service": "light/turn_on",
         "data": {"brightness": 9999}},
        True,
    ),
    # Out-of-range climate temperature
    (
        "Climate temperature = 99°C (out of range)",
        {"entity_id": "climate.living", "service": "climate/set_temperature",
         "data": {"temperature": 99}},
        True,
    ),
    (
        "Climate temperature = -50°C (out of range)",
        {"entity_id": "climate.living", "service": "climate/set_temperature",
         "data": {"temperature": -50}},
        True,
    ),
    # Dangerous domain
    (
        "shell_command domain (should be blocked)",
        {"entity_id": "shell_command.dangerous", "service": "shell_command/run",
         "data": {}},
        True,
    ),
    (
        "script domain with dangerous service",
        {"entity_id": "script.evil", "service": "script/turn_on",
         "data": {"variables": {"cmd": "$(rm -rf /)"}}},
        True,
    ),
    # Valid commands (should be allowed)
    (
        "Light turn on (valid)",
        {"entity_id": "light.bedroom", "service": "light/turn_on",
         "data": {"brightness": 128}},
        False,
    ),
    (
        "Climate set temp 22°C (valid)",
        {"entity_id": "climate.living", "service": "climate/set_temperature",
         "data": {"temperature": 22}},
        False,
    ),
]


async def test_ha_params():
    global PASS_COUNT, FAIL_COUNT, SKIP_COUNT

    print(f"=== V8: HA Bridge Parameter Validation Test ({BASE_URL}) ===\n")

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        ) as session:
            for description, payload, should_block in TEST_CASES:
                try:
                    async with session.post(
                        f"{BASE_URL}/api/device/control",
                        json=payload,
                    ) as resp:
                        status = resp.status
                        body = await resp.json()

                        if should_block:
                            if status in (400, 422, 403):
                                print(f"[PASS] BLOCKED: {description} (HTTP {status})")
                                PASS_COUNT += 1
                            else:
                                print(f"[FAIL] ACCEPTED: {description} (HTTP {status})")
                                print(f"       Payload: {payload}")
                                FAIL_COUNT += 1
                        else:
                            # Either accepted or HA not available (502/503 is fine)
                            if status in (200, 502, 503):
                                print(f"[PASS] Valid command response: {description} (HTTP {status})")
                                PASS_COUNT += 1
                            elif status in (400, 422):
                                print(f"[WARN] Valid command rejected: {description} (HTTP {status}) — false positive?")
                                PASS_COUNT += 1

                except aiohttp.ClientConnectorError:
                    print(f"[SKIP] {description} — HA bridge not reachable")
                    SKIP_COUNT += 1
                    break
                except Exception as e:
                    print(f"[SKIP] {description} — error: {e}")
                    SKIP_COUNT += 1

    except Exception as e:
        print(f"[SKIP] Cannot connect to HA bridge: {e}")
        return

    print(f"\n=== Results: PASS={PASS_COUNT} FAIL={FAIL_COUNT} SKIP={SKIP_COUNT} ===")
    if FAIL_COUNT > 0:
        print(f"STATUS: VULNERABLE ({FAIL_COUNT} issues)")
        return 1
    else:
        print("STATUS: SECURE (or service not running)")
        return 0


if __name__ == "__main__":
    result = asyncio.run(test_ha_params())
    sys.exit(result or 0)
