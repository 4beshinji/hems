#!/usr/bin/env python3
"""
Sensor Data API Integration Test (C.2+)

Tests the 5 sensor API endpoints exposed by the Dashboard backend.
Validates correct JSON structure and graceful empty-data responses.

Requires running: postgres, backend, brain (for events schema population)
Brain must have written to events.* schema (run virtual edge for data).

Test Groups:
  1. /sensors/latest — latest readings + zone filter
  2. /sensors/time-series — window modes (raw / 1h / 1d) + channel filter
  3. /sensors/zones — zone overview snapshot
  4. /sensors/events — world_model event feed + zone filter
  5. /sensors/llm-activity — LLM decision summary
  6. Empty data graceful responses (no 500 errors)
"""
import json
import os
import sys
import urllib.request
import urllib.error

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

passed = 0
failed = 0
skipped = 0


class SkipTest(Exception):
    pass


def api(url, timeout=10):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if "json" in resp.headers.get("Content-Type", ""):
                return json.loads(raw)
            return raw
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"HTTP {e.code}: {error_body}") from e


def test(name, fn):
    global passed, failed, skipped
    try:
        fn()
        passed += 1
        print(f"  PASS  {name}")
    except urllib.error.URLError as e:
        skipped += 1
        print(f"  SKIP  {name} -- service unavailable: {e.reason}")
    except SkipTest as e:
        skipped += 1
        print(f"  SKIP  {name} -- {e}")
    except Exception as e:
        failed += 1
        print(f"  FAIL  {name} -- {e}")


# Track discovered data for dependent tests
_state = {"zones": [], "channels": []}


# ══════════════════════════════════════════════════════════════
# Test 1: /sensors/latest
# ══════════════════════════════════════════════════════════════

def test1_latest_returns_list():
    resp = api(f"{BACKEND_URL}/sensors/latest")
    assert isinstance(resp, list), f"Expected list, got {type(resp)}"
    # Store discovered zones/channels for later tests
    for r in resp:
        if r["zone"] not in _state["zones"]:
            _state["zones"].append(r["zone"])
        if r["channel"] not in _state["channels"]:
            _state["channels"].append(r["channel"])


def test1_latest_structure():
    resp = api(f"{BACKEND_URL}/sensors/latest")
    if not resp:
        raise SkipTest("no sensor data available")
    item = resp[0]
    required = {"timestamp", "zone", "channel", "value"}
    missing = required - set(item.keys())
    assert not missing, f"Missing keys: {missing}"
    assert isinstance(item["value"], (int, float)), \
        f"value should be numeric, got {type(item['value'])}"


def test1_latest_zone_filter():
    if not _state["zones"]:
        raise SkipTest("no zones discovered")
    zone = _state["zones"][0]
    resp = api(f"{BACKEND_URL}/sensors/latest?zone={zone}")
    assert isinstance(resp, list), f"Expected list, got {type(resp)}"
    for item in resp:
        assert item["zone"] == zone, \
            f"Zone filter broken: expected '{zone}', got '{item['zone']}'"


# ══════════════════════════════════════════════════════════════
# Test 2: /sensors/time-series
# ══════════════════════════════════════════════════════════════

def test2_time_series_hourly():
    resp = api(f"{BACKEND_URL}/sensors/time-series?window=1h")
    assert isinstance(resp, dict), f"Expected dict, got {type(resp)}"
    assert "points" in resp, f"Missing 'points' key: {resp.keys()}"
    assert "window" in resp, f"Missing 'window' key"
    assert resp["window"] == "1h", f"Window should be '1h', got '{resp['window']}'"
    assert isinstance(resp["points"], list), \
        f"points should be list, got {type(resp['points'])}"


def test2_time_series_raw():
    resp = api(f"{BACKEND_URL}/sensors/time-series?window=raw")
    assert isinstance(resp, dict), f"Expected dict, got {type(resp)}"
    assert resp["window"] == "raw"
    assert isinstance(resp["points"], list)


def test2_time_series_daily():
    resp = api(f"{BACKEND_URL}/sensors/time-series?window=1d")
    assert isinstance(resp, dict), f"Expected dict, got {type(resp)}"
    assert resp["window"] == "1d"
    assert isinstance(resp["points"], list)


def test2_time_series_point_structure():
    resp = api(f"{BACKEND_URL}/sensors/time-series?window=1h")
    if not resp["points"]:
        raise SkipTest("no time-series data available")
    pt = resp["points"][0]
    required = {"timestamp", "avg", "max", "min"}
    missing = required - set(pt.keys())
    assert not missing, f"Missing point keys: {missing}"


def test2_time_series_channel_filter():
    if not _state["channels"]:
        raise SkipTest("no channels discovered")
    ch = _state["channels"][0]
    resp = api(f"{BACKEND_URL}/sensors/time-series?window=1h&channel={ch}")
    assert resp["channel"] == ch, \
        f"Channel filter not reflected: expected '{ch}', got '{resp['channel']}'"


def test2_time_series_zone_filter():
    if not _state["zones"]:
        raise SkipTest("no zones discovered")
    zone = _state["zones"][0]
    resp = api(f"{BACKEND_URL}/sensors/time-series?window=1h&zone={zone}")
    assert resp["zone"] == zone, \
        f"Zone filter not reflected: expected '{zone}', got '{resp['zone']}'"


# ══════════════════════════════════════════════════════════════
# Test 3: /sensors/zones
# ══════════════════════════════════════════════════════════════

def test3_zones_returns_list():
    resp = api(f"{BACKEND_URL}/sensors/zones")
    assert isinstance(resp, list), f"Expected list, got {type(resp)}"


def test3_zones_structure():
    resp = api(f"{BACKEND_URL}/sensors/zones")
    if not resp:
        raise SkipTest("no zone data available")
    item = resp[0]
    required = {"zone", "channels"}
    missing = required - set(item.keys())
    assert not missing, f"Missing keys: {missing}"
    assert isinstance(item["channels"], dict), \
        f"channels should be dict, got {type(item['channels'])}"


# ══════════════════════════════════════════════════════════════
# Test 4: /sensors/events
# ══════════════════════════════════════════════════════════════

def test4_events_returns_list():
    resp = api(f"{BACKEND_URL}/sensors/events")
    assert isinstance(resp, list), f"Expected list, got {type(resp)}"


def test4_events_structure():
    resp = api(f"{BACKEND_URL}/sensors/events")
    if not resp:
        raise SkipTest("no event data available")
    item = resp[0]
    required = {"timestamp", "zone", "event_type"}
    missing = required - set(item.keys())
    assert not missing, f"Missing keys: {missing}"
    assert item["event_type"].startswith("world_model_"), \
        f"Expected world_model_* event_type, got '{item['event_type']}'"


def test4_events_zone_filter():
    if not _state["zones"]:
        raise SkipTest("no zones discovered")
    zone = _state["zones"][0]
    resp = api(f"{BACKEND_URL}/sensors/events?zone={zone}")
    assert isinstance(resp, list), f"Expected list, got {type(resp)}"
    for item in resp:
        assert item["zone"] == zone, \
            f"Zone filter broken: expected '{zone}', got '{item['zone']}'"


def test4_events_limit():
    resp = api(f"{BACKEND_URL}/sensors/events?limit=3")
    assert isinstance(resp, list), f"Expected list, got {type(resp)}"
    assert len(resp) <= 3, f"Limit not respected: got {len(resp)} items"


# ══════════════════════════════════════════════════════════════
# Test 5: /sensors/llm-activity
# ══════════════════════════════════════════════════════════════

def test5_llm_activity_structure():
    resp = api(f"{BACKEND_URL}/sensors/llm-activity")
    assert isinstance(resp, dict), f"Expected dict, got {type(resp)}"
    required = {"cycles", "total_tool_calls", "avg_duration_sec", "hours"}
    missing = required - set(resp.keys())
    assert not missing, f"Missing keys: {missing}"
    assert isinstance(resp["cycles"], int), f"cycles should be int"
    assert isinstance(resp["total_tool_calls"], int), f"total_tool_calls should be int"
    assert isinstance(resp["avg_duration_sec"], (int, float)), \
        f"avg_duration_sec should be numeric"


def test5_llm_activity_hours_param():
    resp = api(f"{BACKEND_URL}/sensors/llm-activity?hours=1")
    assert resp["hours"] == 1, f"hours param not reflected: {resp['hours']}"


# ══════════════════════════════════════════════════════════════
# Test 6: Empty Data Graceful Responses
# ══════════════════════════════════════════════════════════════

def test6_latest_nonexistent_zone():
    """Non-existent zone should return empty list, not error."""
    resp = api(f"{BACKEND_URL}/sensors/latest?zone=nonexistent_zone_xyz")
    assert isinstance(resp, list), f"Expected list, got {type(resp)}"
    assert len(resp) == 0, f"Expected empty list for fake zone, got {len(resp)} items"


def test6_time_series_nonexistent():
    resp = api(f"{BACKEND_URL}/sensors/time-series?zone=nonexistent_zone_xyz&window=1h")
    assert isinstance(resp, dict), f"Expected dict, got {type(resp)}"
    assert resp["points"] == [], f"Expected empty points for fake zone"


def test6_events_nonexistent_zone():
    resp = api(f"{BACKEND_URL}/sensors/events?zone=nonexistent_zone_xyz")
    assert isinstance(resp, list), f"Expected list, got {type(resp)}"
    assert len(resp) == 0, f"Expected empty list for fake zone"


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main():
    global passed, failed, skipped
    print("=" * 60)
    print("SOMS Sensor Data API Test (C.2+)")
    print("=" * 60)

    print("\n[1] /sensors/latest")
    test("Returns list", test1_latest_returns_list)
    test("Correct item structure", test1_latest_structure)
    test("Zone filter works", test1_latest_zone_filter)

    print("\n[2] /sensors/time-series")
    test("Hourly window (1h)", test2_time_series_hourly)
    test("Raw window", test2_time_series_raw)
    test("Daily window (1d)", test2_time_series_daily)
    test("Point structure (avg/max/min)", test2_time_series_point_structure)
    test("Channel filter", test2_time_series_channel_filter)
    test("Zone filter", test2_time_series_zone_filter)

    print("\n[3] /sensors/zones")
    test("Returns list", test3_zones_returns_list)
    test("Correct zone structure", test3_zones_structure)

    print("\n[4] /sensors/events")
    test("Returns list", test4_events_returns_list)
    test("Correct event structure", test4_events_structure)
    test("Zone filter works", test4_events_zone_filter)
    test("Limit parameter", test4_events_limit)

    print("\n[5] /sensors/llm-activity")
    test("Response structure", test5_llm_activity_structure)
    test("Hours parameter", test5_llm_activity_hours_param)

    print("\n[6] Empty Data / Graceful Responses")
    test("Latest with nonexistent zone", test6_latest_nonexistent_zone)
    test("Time-series with nonexistent zone", test6_time_series_nonexistent)
    test("Events with nonexistent zone", test6_events_nonexistent_zone)

    # Summary
    total = passed + failed + skipped
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped / {total} total")
    print(f"{'=' * 60}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
