#!/usr/bin/env python3
"""Phase 1.5 E2E test — device stake funding & proportional rewards."""

import urllib.request
import json
import sys

API = "http://localhost:8000"
all_ok = True


def post(path, data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        f"{API}{path}", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(path):
    resp = urllib.request.urlopen(f"{API}{path}")
    return resp.status, json.loads(resp.read())


def check(label, status, body, expect_status=200):
    global all_ok
    ok = "pass" if status == expect_status else "FAIL"
    print(f"  [{ok}] {label}: {status}", flush=True)
    if status != expect_status:
        detail = json.dumps(body, ensure_ascii=False)[:200]
        print(f"    BODY: {detail}", flush=True)
        all_ok = False
        return False
    return True


def assert_eq(label, actual, expected):
    global all_ok
    ok = actual == expected
    tag = "pass" if ok else "FAIL"
    print(f"  [{tag}] {label}: {actual} (expect {expected})", flush=True)
    if not ok:
        all_ok = False
    return ok


# ============= 1. Setup =============
print("== 1. Setup: wallets + seed balance ==", flush=True)
s, b = post("/wallets/", {"user_id": 1})
check("Create wallet user 1", s, b)

s, b = post("/wallets/", {"user_id": 2})
check("Create wallet user 2", s, b)

s, b = post("/transactions/task-reward", {
    "user_id": 2, "amount": 50000, "task_id": 999, "description": "seed",
})
check("Seed user 2 balance (50000)", s, b)

# ============= 2. Device Registration =============
print("\n== 2. Device Registration ==", flush=True)
s, b = post("/devices/", {
    "device_id": "test_01", "owner_id": 1, "device_type": "sensor_node",
})
check("Register device test_01", s, b)

if s == 200:
    for field in ["total_shares", "available_shares", "share_price",
                   "funding_open", "utility_score"]:
        has = field in b
        tag = "pass" if has else "FAIL"
        print(f"  [{tag}] DeviceResponse has '{field}'", flush=True)
        if not has:
            all_ok = False

# ============= 3. Funding Open =============
print("\n== 3. Open Funding (50 shares @ 100) ==", flush=True)
s, b = post("/devices/test_01/funding/open", {
    "owner_id": 1, "shares_to_list": 50, "share_price": 100,
})
check("Open funding", s, b)
if s == 200:
    assert_eq("available_shares", b.get("available_shares"), 50)
    assert_eq("funding_open", b.get("funding_open"), True)
    assert_eq("share_price", b.get("share_price"), 100)

# ============= 4. Buy Shares =============
print("\n== 4. Buy Shares (user 2 buys 10 shares) ==", flush=True)
s, b = post("/devices/test_01/stakes/buy", {"user_id": 2, "shares": 10})
check("Buy 10 shares", s, b)
if s == 200:
    assert_eq("stake.shares", b.get("shares"), 10)
    assert_eq("stake.percentage", b.get("percentage"), 10.0)

# Balances: user 2 paid 10 * 100 = 1000 -> owner
s, b1 = get("/wallets/1")
s, b2 = get("/wallets/2")
assert_eq("user 1 balance (received 1000)", b1.get("balance"), 1000)
assert_eq("user 2 balance (50000 - 1000)", b2.get("balance"), 49000)

# ============= 5. Stakeholders =============
print("\n== 5. Get Stakeholders ==", flush=True)
s, b = get("/devices/test_01/stakes")
check("Get stakes", s, b)
if s == 200:
    holders = b.get("stakeholders", [])
    assert_eq("stakeholder count", len(holders), 2)
    for sh in holders:
        uid = sh["user_id"]
        print(f"    user={uid}, shares={sh['shares']}, pct={sh['percentage']}%", flush=True)
    avail = b.get("available_shares")
    assert_eq("available_shares after buy", avail, 40)

# ============= 6. Heartbeat #1 (sets timestamp, no reward) =============
print("\n== 6. Heartbeat #1 (initial) ==", flush=True)
s, b = post("/devices/test_01/heartbeat")
check("Heartbeat #1", s, b)
assert_eq("reward (first beat = 0)", b.get("reward_granted"), 0)

# ============= 7. Portfolio =============
print("\n== 7. User 2 Portfolio ==", flush=True)
s, b = get("/users/2/portfolio")
check("Get portfolio", s, b)
if s == 200:
    stakes = b.get("stakes", [])
    assert_eq("portfolio stakes count", len(stakes), 1)
    if stakes:
        entry = stakes[0]
        assert_eq("portfolio device_id", entry.get("device_id"), "test_01")
        assert_eq("portfolio shares", entry.get("shares"), 10)
        assert_eq("portfolio percentage", entry.get("percentage"), 10.0)

# ============= 8. Utility Score =============
print("\n== 8. Utility Score ==", flush=True)
s, b = post("/devices/test_01/utility-score", {"score": 1.5})
check("Set utility_score=1.5", s, b)
if s == 200:
    assert_eq("utility_score", b.get("utility_score"), 1.5)

# Clamp test: > 2.0 -> 2.0
s, b = post("/devices/test_01/utility-score", {"score": 5.0})
check("Clamp utility_score=5.0", s, b)
if s == 200:
    assert_eq("clamped to 2.0", b.get("utility_score"), 2.0)

# Clamp test: < 0.5 -> 0.5
s, b = post("/devices/test_01/utility-score", {"score": 0.1})
check("Clamp utility_score=0.1", s, b)
if s == 200:
    assert_eq("clamped to 0.5", b.get("utility_score"), 0.5)

# Reset to 1.0
post("/devices/test_01/utility-score", {"score": 1.0})

# ============= 9. Heartbeat with metrics =============
print("\n== 9. Heartbeat with metrics body ==", flush=True)
s, b = post("/devices/test_01/heartbeat", {
    "power_mode": "DEEP_SLEEP", "battery_pct": 75, "hops_to_mqtt": 2,
})
check("Heartbeat with body", s, b)
reward = b.get("reward_granted", 0)
uptime = b.get("uptime_seconds", 0)
print(f"    reward={reward}, uptime={uptime}s", flush=True)

# Verify metrics persisted
s, devs = get("/devices/")
if s == 200:
    test_dev = next((d for d in devs if d["device_id"] == "test_01"), None)
    if test_dev:
        assert_eq("power_mode", test_dev.get("power_mode"), "DEEP_SLEEP")
        assert_eq("battery_pct", test_dev.get("battery_pct"), 75)
        assert_eq("hops_to_mqtt", test_dev.get("hops_to_mqtt"), 2)

# ============= 10. Share Return =============
print("\n== 10. Share Return (user 2 returns 5 shares) ==", flush=True)
_, b_before = get("/wallets/2")
s, b = post("/devices/test_01/stakes/return", {"user_id": 2, "shares": 5})
check("Return 5 shares", s, b)
if s == 200:
    assert_eq("remaining shares", b.get("shares"), 5)

_, b_after = get("/wallets/2")
refund = b_after.get("balance", 0) - b_before.get("balance", 0)
assert_eq("refund amount (5 * 100)", refund, 500)

# Verify stakeholder list updated
s, b = get("/devices/test_01/stakes")
if s == 200:
    user2_stake = next(
        (sh for sh in b.get("stakeholders", []) if sh["user_id"] == 2), None,
    )
    if user2_stake:
        assert_eq("user 2 shares after return", user2_stake.get("shares"), 5)
    avail = b.get("available_shares")
    assert_eq("available_shares after return", avail, 45)

# ============= 11. Error cases =============
print("\n== 11. Error cases ==", flush=True)

# Non-owner cannot open funding
s, b = post("/devices/test_01/funding/close", {"owner_id": 999})
assert_eq("non-owner close -> 400", s, 400)

# Buy more than available
s, b = post("/devices/test_01/stakes/buy", {"user_id": 2, "shares": 999})
assert_eq("buy > available -> 400", s, 400)

# Return more than held
s, b = post("/devices/test_01/stakes/return", {"user_id": 2, "shares": 999})
assert_eq("return > held -> 400", s, 400)

# Owner cannot return shares
s, b = post("/devices/test_01/stakes/return", {"user_id": 1, "shares": 1})
assert_eq("owner return -> 400", s, 400)

# ============= 12. Close Funding =============
print("\n== 12. Close Funding ==", flush=True)
s, b = post("/devices/test_01/funding/close", {"owner_id": 1})
check("Close funding", s, b)
if s == 200:
    assert_eq("funding_open=False", b.get("funding_open"), False)
    assert_eq("available_shares=0 (reclaimed)", b.get("available_shares"), 0)

# Buy after close -> error
s, b = post("/devices/test_01/stakes/buy", {"user_id": 2, "shares": 1})
assert_eq("buy after close -> 400", s, 400)

# ============= 13. Pool (Model B) =============
print("\n== 13. Pool Funding (Model B) ==", flush=True)

# Create pool
s, b = post("/admin/pools", {
    "title": "Temperature Sensor #3", "goal_jpy": 3000,
})
check("Create pool", s, b)
pool_id = b.get("id")
assert_eq("pool status", b.get("status"), "open")

# Contribute
s, b = post(f"/admin/pools/{pool_id}/contribute", {"user_id": 10, "amount_jpy": 1500})
check("Contribute user 10", s, b)

s, b = post(f"/admin/pools/{pool_id}/contribute", {"user_id": 11, "amount_jpy": 1500})
check("Contribute user 11", s, b)

# Check pool is funded
s, b = get(f"/admin/pools/{pool_id}")
check("Get pool detail", s, b)
if s == 200:
    assert_eq("pool status after goal", b.get("status"), "funded")
    assert_eq("raised_jpy", b.get("raised_jpy"), 3000)
    assert_eq("contributions count", len(b.get("contributions", [])), 2)

# Public pool list
s, b = get("/pools")
check("Public pool list", s, b)
if s == 200:
    assert_eq("public pool count >= 1", len(b) >= 1, True)

# Register a new device for pool activation
s, _ = post("/devices/", {
    "device_id": "pool_dev_01", "owner_id": 1, "device_type": "sensor_node",
})
check("Register pool device", s, _)

# Activate pool
s, b = post(f"/admin/pools/{pool_id}/activate", {"device_id": "pool_dev_01"})
check("Activate pool", s, b)
if s == 200:
    assert_eq("pool status active", b.get("status"), "active")
    contribs = b.get("contributions", [])
    total_allocated = sum(c.get("shares_allocated", 0) for c in contribs)
    assert_eq("total shares allocated", total_allocated, 100)
    for c in contribs:
        uid = c["user_id"]
        shares = c["shares_allocated"]
        print(f"    user={uid}, shares_allocated={shares}", flush=True)

# ============= SUMMARY =============
print(f"\n{'=' * 50}", flush=True)
if all_ok:
    print("ALL TESTS PASSED", flush=True)
else:
    print("SOME TESTS FAILED", flush=True)
sys.exit(0 if all_ok else 1)
