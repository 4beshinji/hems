#!/usr/bin/env python3
"""
Wallet <-> Dashboard E2E Test: cross-service integration paths.

Tests the integration paths where Dashboard backend internally calls
Wallet service during task lifecycle operations.

Requires running: postgres, backend, wallet, mosquitto
Wallet port 8003 must be exposed for balance verification.

Test Groups:
  1. Zone multiplier affects bounty (~2.0x payout)
  2. MQTT task report published on completion
  3. Concurrent task completions (5 parallel)
  4. Device XP accumulates across multiple tasks
  5. No bounty without assignment
"""
import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import paho.mqtt.client as mqtt

    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
WALLET_URL = os.getenv("WALLET_URL", "http://localhost:8003")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("SOMS_PORT_MQTT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "soms")
MQTT_PASS = os.getenv("MQTT_PASS", "soms_dev_mqtt")

# Unique suffix to avoid collisions across test runs
_TS = str(int(time.time()))[-6:]

passed = 0
failed = 0
skipped = 0


class SkipTest(Exception):
    pass


# ── HTTP helper ──────────────────────────────────────────────

def api(url, method="GET", data=None, timeout=10):
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
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


# ── Shared helpers ───────────────────────────────────────────

def ensure_user_wallet(suffix):
    """Create user via backend + ensure wallet exists via wallet service."""
    username = f"e2e_{suffix}_{_TS}"
    try:
        user = api(f"{BACKEND_URL}/users/", method="POST", data={
            "username": username,
            "display_name": f"E2E {suffix}",
        })
    except RuntimeError as e:
        if "409" in str(e):
            users = api(f"{BACKEND_URL}/users/?limit=200")
            user = next(u for u in users if u["username"] == username)
        else:
            raise
    uid = user["id"]
    try:
        api(f"{WALLET_URL}/wallets/", method="POST", data={"user_id": uid})
    except RuntimeError:
        pass  # already exists
    return user


def create_task(title, bounty, zone, location=None, task_type=None):
    return api(f"{BACKEND_URL}/tasks/", method="POST", data={
        "title": title,
        "description": "E2E test task",
        "bounty_gold": bounty,
        "bounty_xp": 50,
        "urgency": 2,
        "zone": zone,
        "location": location or zone,
        "task_type": task_type or ["e2e_test"],
    })


def accept_task(task_id, user_id):
    return api(f"{BACKEND_URL}/tasks/{task_id}/accept", method="PUT", data={
        "user_id": user_id,
    })


def complete_task(task_id, report_status=None, completion_note=None):
    data = {}
    if report_status:
        data["report_status"] = report_status
    if completion_note:
        data["completion_note"] = completion_note
    return api(
        f"{BACKEND_URL}/tasks/{task_id}/complete",
        method="PUT",
        data=data if data else None,
    )


def get_balance(user_id):
    return api(f"{WALLET_URL}/wallets/{user_id}")["balance"]


def get_history(user_id, limit=50):
    return api(f"{WALLET_URL}/wallets/{user_id}/history?limit={limit}")


def register_device(device_id, owner_id, zone, device_type="sensor_node"):
    return api(f"{WALLET_URL}/devices/", method="POST", data={
        "device_id": device_id,
        "owner_id": owner_id,
        "device_type": device_type,
        "display_name": f"E2E Device {device_id}",
        "topic_prefix": f"office/{zone}/sensor/{device_id}",
    })


def grant_xp(zone, task_id, xp_amount, event_type="manual"):
    return api(f"{WALLET_URL}/devices/xp-grant", method="POST", data={
        "zone": zone,
        "task_id": task_id,
        "xp_amount": xp_amount,
        "event_type": event_type,
    })


# ══════════════════════════════════════════════════════════════
# Test 1: Zone Multiplier Affects Bounty (~2.0x payout)
# ══════════════════════════════════════════════════════════════

state1 = {}


def test1_setup():
    zone = f"e2e_mult_{_TS}"
    state1["zone"] = zone
    user = ensure_user_wallet("mult")
    state1["uid"] = user["id"]
    dev_id = f"e2e_dev_mult_{_TS}"
    register_device(dev_id, user["id"], zone)
    state1["device_id"] = dev_id
    state1["balance_before"] = get_balance(user["id"])


def test1_grant_xp():
    if "uid" not in state1:
        raise SkipTest("setup skipped")
    # Grant 2000 XP -> multiplier = 1.0 + (2000/1000)*0.5 = 2.0x
    resp = grant_xp(state1["zone"], 0, 2000, "manual_e2e")
    assert resp["devices_awarded"] >= 1, f"No devices awarded: {resp}"
    assert state1["device_id"] in resp["device_ids"], f"Device missing: {resp}"


def test1_verify_multiplier():
    if "uid" not in state1:
        raise SkipTest("setup skipped")
    resp = api(f"{WALLET_URL}/devices/zone-multiplier/{state1['zone']}")
    assert resp["device_count"] >= 1, f"No devices: {resp}"
    # 2000 XP -> multiplier = 2.0
    assert resp["multiplier"] >= 1.9, f"Multiplier too low: {resp['multiplier']}"


def test1_task_lifecycle():
    if "uid" not in state1:
        raise SkipTest("setup skipped")
    task = create_task(f"Multiplier E2E {_TS}", 1000, state1["zone"])
    state1["task_id"] = task["id"]
    accept_task(task["id"], state1["uid"])
    # At this point device has 2000 (manual) + 10 (task_created) = 2010 XP
    complete_task(task["id"])
    # Backend: XP grant +20 (task_completed) -> 2030 XP, THEN fetch multiplier
    # multiplier = 1.0 + (2030/1000)*0.5 = 2.015
    # adjusted_bounty = int(1000 * 2.015) = 2015
    time.sleep(0.5)  # let fire-and-forget wallet payment settle


def test1_verify_bounty():
    if "task_id" not in state1:
        raise SkipTest("lifecycle skipped")
    balance_after = get_balance(state1["uid"])
    bounty_received = balance_after - state1["balance_before"]
    state1["bounty_received"] = bounty_received
    # Expect ~2015 (1000 * 2.015x), allow tolerance for timing
    assert bounty_received >= 1800, \
        f"Bounty too low: {bounty_received} (expected ~2000)"
    assert bounty_received <= 2200, \
        f"Bounty too high: {bounty_received} (expected ~2000)"


def test1_verify_ledger():
    if "bounty_received" not in state1:
        raise SkipTest("bounty verification skipped")
    history = get_history(state1["uid"], limit=10)
    rewards = [
        e for e in history
        if e["transaction_type"] == "TASK_REWARD" and e["amount"] > 0
    ]
    assert len(rewards) >= 1, f"No TASK_REWARD credit entries: {history}"
    latest = rewards[0]
    assert latest["amount"] == state1["bounty_received"], \
        f"Ledger amount {latest['amount']} != balance change {state1['bounty_received']}"


# ══════════════════════════════════════════════════════════════
# Test 2: MQTT Task Report Published on Completion
# ══════════════════════════════════════════════════════════════


def test2_mqtt_report():
    if not HAS_MQTT:
        raise SkipTest("paho-mqtt not installed")

    zone = f"e2e_mqtt_{_TS}"
    user = ensure_user_wallet("mqtt")

    task = create_task(f"MQTT Report E2E {_TS}", 500, zone)
    task_id = task["id"]
    accept_task(task_id, user["id"])

    # Subscribe BEFORE completing
    received = []
    connected = threading.Event()

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except (AttributeError, TypeError):
        client = mqtt.Client()

    def on_connect(client, userdata, flags, *args):
        client.subscribe(f"office/{zone}/task_report/#")
        connected.set()

    def on_message(client, userdata, msg):
        received.append(json.loads(msg.payload.decode()))

    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()

    try:
        assert connected.wait(timeout=5), "MQTT connection timeout"
        time.sleep(0.3)  # let subscription settle

        complete_task(task_id, report_status="resolved", completion_note="テスト完了")

        deadline = time.time() + 5
        while not received and time.time() < deadline:
            time.sleep(0.1)

        assert len(received) >= 1, "No MQTT task report received within 5s"
        msg = received[0]
        assert msg["task_id"] == task_id, f"task_id mismatch: {msg}"
        assert msg["title"] == f"MQTT Report E2E {_TS}", f"title mismatch: {msg}"
        assert msg["report_status"] == "resolved", f"report_status: {msg}"
        assert msg["completion_note"] == "テスト完了", f"completion_note: {msg}"
    finally:
        client.loop_stop()
        client.disconnect()


# ══════════════════════════════════════════════════════════════
# Test 3: Concurrent Task Completions (5 parallel)
# ══════════════════════════════════════════════════════════════

state3 = {}


def test3_setup():
    zone = f"e2e_conc_{_TS}"
    state3["zone"] = zone
    user = ensure_user_wallet("conc")
    state3["uid"] = user["id"]
    state3["balance_before"] = get_balance(user["id"])

    task_ids = []
    for i in range(5):
        task = create_task(
            f"Concurrent E2E {i} {_TS}",
            500,
            zone,
            location=f"{zone}_loc_{i}",
            task_type=[f"e2e_conc_{i}"],  # unique type to avoid dedup
        )
        accept_task(task["id"], user["id"])
        task_ids.append(task["id"])
    state3["task_ids"] = task_ids


def test3_concurrent_complete():
    if "task_ids" not in state3:
        raise SkipTest("setup skipped")

    def do_complete(tid):
        return complete_task(tid)

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(do_complete, tid): tid for tid in state3["task_ids"]}
        for f in as_completed(futures):
            resp = f.result()
            assert resp["is_completed"] is True, \
                f"Task {futures[f]} not completed"
    time.sleep(1.0)  # let all fire-and-forget wallet payments settle


def test3_verify_balance():
    if "uid" not in state3:
        raise SkipTest("setup skipped")
    balance_after = get_balance(state3["uid"])
    total_received = balance_after - state3["balance_before"]
    # 5 x 500 x multiplier (>=1.0) = at least 2500
    assert total_received >= 2500, \
        f"Total received {total_received} too low (expected >= 2500 for 5x500)"


def test3_verify_ledger():
    if "uid" not in state3:
        raise SkipTest("setup skipped")
    history = get_history(state3["uid"], limit=50)
    rewards = [
        e for e in history
        if e["transaction_type"] == "TASK_REWARD" and e["amount"] > 0
    ]
    assert len(rewards) >= 5, \
        f"Expected >= 5 TASK_REWARD credits, got {len(rewards)}"


# ══════════════════════════════════════════════════════════════
# Test 4: Device XP Accumulates Across Multiple Tasks
# ══════════════════════════════════════════════════════════════

state4 = {}


def test4_setup():
    zone = f"e2e_xpacc_{_TS}"
    state4["zone"] = zone
    user = ensure_user_wallet("xpacc")
    state4["uid"] = user["id"]
    dev_id = f"e2e_dev_xpacc_{_TS}"
    register_device(dev_id, user["id"], zone)
    state4["device_id"] = dev_id


def test4_task_cycle_1():
    if "uid" not in state4:
        raise SkipTest("setup skipped")
    zone = state4["zone"]
    task = create_task(f"XP Accum E2E 1 {_TS}", 500, zone)
    accept_task(task["id"], state4["uid"])
    complete_task(task["id"])
    time.sleep(0.3)


def test4_task_cycle_2():
    if "uid" not in state4:
        raise SkipTest("setup skipped")
    zone = state4["zone"]
    task = create_task(
        f"XP Accum E2E 2 {_TS}", 500, zone,
        location=f"{zone}_loc2",
        task_type=["e2e_xpacc_2"],  # unique type to avoid dedup
    )
    accept_task(task["id"], state4["uid"])
    complete_task(task["id"])
    time.sleep(0.3)


def test4_verify_xp():
    # Each task: 10 XP (create) + 20 XP (complete) = 30 XP
    # Two tasks -> 60 XP minimum
    devices = api(f"{WALLET_URL}/devices/")
    dev = next(
        (d for d in devices if d["device_id"] == state4["device_id"]), None
    )
    assert dev is not None, f"Device not found: {state4['device_id']}"
    assert dev["xp"] >= 40, \
        f"XP too low: {dev['xp']} (expected >= 40 from 2 tasks)"
    state4["final_xp"] = dev["xp"]


def test4_verify_multiplier():
    resp = api(f"{WALLET_URL}/devices/zone-multiplier/{state4['zone']}")
    assert resp["device_count"] >= 1, f"No devices in zone: {resp}"
    assert resp["avg_xp"] >= 40, f"avg_xp too low: {resp['avg_xp']}"
    assert resp["multiplier"] >= 1.0, \
        f"Multiplier should be >= 1.0: {resp['multiplier']}"


# ══════════════════════════════════════════════════════════════
# Test 5: No Bounty Without Assignment
# ══════════════════════════════════════════════════════════════

state5 = {}


def test5_setup():
    zone = f"e2e_noassign_{_TS}"
    state5["zone"] = zone
    user = ensure_user_wallet("noassign")
    state5["uid"] = user["id"]
    state5["balance_before"] = get_balance(user["id"])


def test5_complete_without_accept():
    task = create_task(f"No Assign E2E {_TS}", 1000, state5["zone"])
    state5["task_id"] = task["id"]
    # Do NOT accept -- complete directly
    resp = complete_task(task["id"])
    assert resp["is_completed"] is True, f"Task not completed: {resp}"
    assert resp["assigned_to"] is None, f"Should have no assignee: {resp}"
    time.sleep(0.5)


def test5_verify_no_bounty():
    if "uid" not in state5:
        raise SkipTest("setup skipped")
    balance_after = get_balance(state5["uid"])
    assert balance_after == state5["balance_before"], \
        f"Balance changed without assignment: {state5['balance_before']} -> {balance_after}"


def test5_verify_no_reward_entry():
    if "uid" not in state5:
        raise SkipTest("setup skipped")
    history = get_history(state5["uid"], limit=50)
    # This user was created fresh and never accepted a task,
    # so there should be zero TASK_REWARD entries
    task_rewards = [
        e for e in history
        if e["transaction_type"] == "TASK_REWARD" and e["amount"] > 0
    ]
    assert len(task_rewards) == 0, \
        f"Unexpected TASK_REWARD for unassigned user: {task_rewards}"


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main():
    global passed, failed, skipped
    print("=" * 60)
    print("SOMS Wallet <-> Dashboard E2E Test")
    print("=" * 60)

    print("\n[1] Zone Multiplier Affects Bounty (~2.0x)")
    test("Setup (user + device + wallet)", test1_setup)
    test("Grant 2000 XP to zone device", test1_grant_xp)
    test("Zone multiplier >= 1.9x", test1_verify_multiplier)
    test("Task lifecycle (create->accept->complete)", test1_task_lifecycle)
    test("Bounty ~2000 (1000 x ~2.0x)", test1_verify_bounty)
    test("Ledger TASK_REWARD matches adjusted bounty", test1_verify_ledger)

    print("\n[2] MQTT Task Report on Completion")
    test("Task report published with correct payload", test2_mqtt_report)

    print("\n[3] Concurrent Task Completions (5 parallel)")
    test("Setup (5 tasks, all accepted)", test3_setup)
    test("Complete all 5 concurrently", test3_concurrent_complete)
    test("Wallet balance increased by >= 5x500", test3_verify_balance)
    test("5 distinct TASK_REWARD entries in ledger", test3_verify_ledger)

    print("\n[4] Device XP Accumulates Across Tasks")
    test("Setup (user + device)", test4_setup)
    test("Task cycle 1 (create->accept->complete)", test4_task_cycle_1)
    test("Task cycle 2 (create->accept->complete)", test4_task_cycle_2)
    test("Device XP >= 40 (2 x 20 XP minimum)", test4_verify_xp)
    test("Zone multiplier reflects cumulative XP", test4_verify_multiplier)

    print("\n[5] No Bounty Without Assignment")
    test("Setup (user + wallet)", test5_setup)
    test("Complete task without accepting", test5_complete_without_accept)
    test("Wallet balance unchanged", test5_verify_no_bounty)
    test("No TASK_REWARD in ledger", test5_verify_no_reward_entry)

    # Summary
    total = passed + failed + skipped
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped / {total} total")
    print(f"{'=' * 60}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
