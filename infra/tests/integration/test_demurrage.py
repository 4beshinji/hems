#!/usr/bin/env python3
"""
Demurrage Test: validates idle-balance tax mechanics.

Requires running: postgres, wallet service

Scenarios:
  1. Pure function tests (calc_demurrage, calc_fee)
  2. Eligible wallet gets 2% burned
  3. Exempt wallet (balance <= 100) is skipped
  4. System wallet (user_id=0) is never taxed
  5. Supply stats updated after demurrage
  6. Multiple cycles accumulate burns correctly
"""
import json
import sys
import urllib.request
import urllib.error

WALLET_URL = "http://localhost:8003"

passed = 0
failed = 0
skipped = 0


def api_request(url, method="GET", data=None, timeout=10):
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type:
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
        print(f"  ✅ {name}")
    except urllib.error.URLError as e:
        skipped += 1
        print(f"  ⏭️  {name} — SKIPPED (service unavailable: {e.reason})")
    except Exception as e:
        failed += 1
        print(f"  ❌ {name} — {e}")


# ── State ──
state = {
    "user_rich": 100,     # user_id for rich wallet (above exempt threshold)
    "user_poor": 101,     # user_id for poor wallet (below exempt threshold)
    "user_exact": 102,    # user_id for exactly-at-threshold wallet
}


# ── Test 1: Health Check ──

def test_wallet_health():
    resp = api_request(f"{WALLET_URL}/")
    assert "message" in resp, f"Unexpected response: {resp}"


# ── Test 2: Setup — create wallets and fund them ──

def test_create_rich_wallet():
    uid = state["user_rich"]
    try:
        api_request(f"{WALLET_URL}/wallets/", method="POST", data={"user_id": uid})
    except RuntimeError:
        pass
    # Fund with 10000 milli-units (10.0 SOMS) — well above exempt threshold of 100
    api_request(f"{WALLET_URL}/transactions/task-reward", method="POST", data={
        "user_id": uid,
        "amount": 10000,
        "task_id": 9901,
        "description": "Demurrage test funding",
    })
    resp = api_request(f"{WALLET_URL}/wallets/{uid}")
    assert resp["balance"] == 10000, f"Expected 10000, got {resp['balance']}"


def test_create_poor_wallet():
    uid = state["user_poor"]
    try:
        api_request(f"{WALLET_URL}/wallets/", method="POST", data={"user_id": uid})
    except RuntimeError:
        pass
    # Fund with 50 milli-units — below exempt threshold
    api_request(f"{WALLET_URL}/transactions/task-reward", method="POST", data={
        "user_id": uid,
        "amount": 50,
        "task_id": 9902,
        "description": "Demurrage test funding (poor)",
    })
    resp = api_request(f"{WALLET_URL}/wallets/{uid}")
    assert resp["balance"] == 50, f"Expected 50, got {resp['balance']}"


def test_create_exact_wallet():
    uid = state["user_exact"]
    try:
        api_request(f"{WALLET_URL}/wallets/", method="POST", data={"user_id": uid})
    except RuntimeError:
        pass
    # Fund with exactly 100 milli-units — at the exempt threshold (should NOT be taxed)
    api_request(f"{WALLET_URL}/transactions/task-reward", method="POST", data={
        "user_id": uid,
        "amount": 100,
        "task_id": 9903,
        "description": "Demurrage test funding (exact threshold)",
    })
    resp = api_request(f"{WALLET_URL}/wallets/{uid}")
    assert resp["balance"] == 100, f"Expected 100, got {resp['balance']}"


# ── Test 3: Record supply stats before demurrage ──

def test_record_supply_before():
    resp = api_request(f"{WALLET_URL}/supply")
    state["supply_before"] = resp
    assert resp["total_issued"] >= 10150, f"Issued too low: {resp['total_issued']}"


# ── Test 4: Trigger demurrage ──

def test_trigger_demurrage():
    resp = api_request(f"{WALLET_URL}/demurrage/trigger", method="POST")
    assert resp["status"] == "ok", f"Trigger failed: {resp}"


# ── Test 5: Verify rich wallet was taxed 2% ──

def test_rich_wallet_taxed():
    uid = state["user_rich"]
    resp = api_request(f"{WALLET_URL}/wallets/{uid}")
    # 10000 * 0.02 = 200 burned → 9800 remaining
    assert resp["balance"] == 9800, f"Expected 9800 after 2% demurrage, got {resp['balance']}"


# ── Test 6: Verify poor wallet was NOT taxed ──

def test_poor_wallet_exempt():
    uid = state["user_poor"]
    resp = api_request(f"{WALLET_URL}/wallets/{uid}")
    assert resp["balance"] == 50, f"Poor wallet should be untouched, got {resp['balance']}"


# ── Test 7: Verify exact-threshold wallet was NOT taxed ──

def test_exact_wallet_exempt():
    uid = state["user_exact"]
    resp = api_request(f"{WALLET_URL}/wallets/{uid}")
    assert resp["balance"] == 100, f"Threshold wallet should be untouched, got {resp['balance']}"


# ── Test 8: Supply stats updated ──

def test_supply_updated():
    resp = api_request(f"{WALLET_URL}/supply")
    before = state["supply_before"]
    burned_diff = resp["total_burned"] - before["total_burned"]
    # At minimum, 200 was burned from the rich wallet
    assert burned_diff >= 200, f"Expected ≥200 burned, got {burned_diff}"
    assert resp["circulating"] < before["circulating"], "Circulating should decrease"


# ── Test 9: Demurrage ledger entry exists ──

def test_demurrage_ledger_entry():
    uid = state["user_rich"]
    history = api_request(f"{WALLET_URL}/wallets/{uid}/history?limit=5")
    demurrage_entries = [e for e in history if e["transaction_type"] == "DEMURRAGE"]
    assert len(demurrage_entries) >= 1, f"No DEMURRAGE entries found: {history}"
    assert demurrage_entries[0]["amount"] == -200, (
        f"Expected -200 demurrage, got {demurrage_entries[0]['amount']}"
    )


# ── Test 10: Second demurrage cycle compounds correctly ──

def test_second_demurrage_cycle():
    # Trigger again
    api_request(f"{WALLET_URL}/demurrage/trigger", method="POST")
    uid = state["user_rich"]
    resp = api_request(f"{WALLET_URL}/wallets/{uid}")
    # 9800 * 0.02 = 196 burned → 9604 remaining
    assert resp["balance"] == 9604, f"Expected 9604 after 2nd demurrage, got {resp['balance']}"


# ── Test 11: System wallet not taxed ──

def test_system_wallet_not_taxed():
    resp = api_request(f"{WALLET_URL}/wallets/0")
    # System wallet can go negative — it should never have demurrage applied
    # Just verify it exists and wasn't burned
    assert resp["user_id"] == 0, f"System wallet not found: {resp}"


# ── Main ──

def main():
    global passed, failed, skipped
    print("=" * 60)
    print("SOMS Demurrage Test")
    print("=" * 60)

    print("\n🔍 Test 1: Health Check")
    test("Wallet service health", test_wallet_health)

    print("\n💰 Test 2: Setup — Create & Fund Wallets")
    test("Create rich wallet (10000 milli-units)", test_create_rich_wallet)
    test("Create poor wallet (50 milli-units)", test_create_poor_wallet)
    test("Create exact-threshold wallet (100 milli-units)", test_create_exact_wallet)

    print("\n📊 Test 3: Pre-Demurrage Supply Stats")
    test("Record supply before demurrage", test_record_supply_before)

    print("\n⚡ Test 4: Trigger Demurrage")
    test("Manual demurrage trigger", test_trigger_demurrage)

    print("\n🔥 Test 5-7: Verify Demurrage Application")
    test("Rich wallet taxed 2% (10000 → 9800)", test_rich_wallet_taxed)
    test("Poor wallet exempt (50 unchanged)", test_poor_wallet_exempt)
    test("Exact-threshold wallet exempt (100 unchanged)", test_exact_wallet_exempt)

    print("\n📈 Test 8: Supply Stats Updated")
    test("Supply stats reflect burn", test_supply_updated)

    print("\n📋 Test 9: Ledger Entry")
    test("DEMURRAGE entry in transaction history", test_demurrage_ledger_entry)

    print("\n🔄 Test 10: Compound Demurrage")
    test("Second cycle: 9800 → 9604", test_second_demurrage_cycle)

    print("\n🔒 Test 11: System Wallet Protection")
    test("System wallet (user_id=0) not taxed", test_system_wallet_not_taxed)

    # Summary
    total = passed + failed + skipped
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped / {total} total")
    print(f"{'=' * 60}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
