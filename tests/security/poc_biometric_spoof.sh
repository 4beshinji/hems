#!/usr/bin/env bash
# PoC V5: Biometric webhook 認証なしテスト
# 認証なしで偽バイオメトリクスデータを注入できるか確認

set -euo pipefail

BIO_HOST="${BIO_HOST:-127.0.0.1}"
BIO_PORT="${BIO_PORT:-8017}"
TIMEOUT=5

PASS=0
FAIL=0
SKIP=0

BASE_URL="http://${BIO_HOST}:${BIO_PORT}"

check_endpoint() {
    local description="$1"
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" \
        --connect-timeout "$TIMEOUT" \
        "${@:2}" 2>/dev/null || echo "000")

    case "$status" in
        000)
            echo "[SKIP] $description — service not reachable"
            SKIP=$((SKIP + 1))
            ;;
        200|201|202)
            echo "[FAIL] $description — accepted without auth (HTTP $status)"
            FAIL=$((FAIL + 1))
            ;;
        401|403)
            echo "[PASS] $description — rejected with HTTP $status"
            PASS=$((PASS + 1))
            ;;
        *)
            echo "[INFO] $description — HTTP $status (unexpected)"
            SKIP=$((SKIP + 1))
            ;;
    esac
}

echo "=== V5: Biometric Webhook Auth Test (${BASE_URL}) ==="
echo ""

# 1. Fake high heart rate (would trigger alert)
check_endpoint "Fake HR=250 injection (no auth)" \
    -X POST "${BASE_URL}/api/biometric/webhook" \
    -H "Content-Type: application/json" \
    -d '{"heart_rate": 250, "timestamp": 1700000000}'

# 2. Fake low SpO2 (would trigger emergency alert)
check_endpoint "Fake SpO2=70 injection (no auth)" \
    -X POST "${BASE_URL}/api/biometric/webhook" \
    -H "Content-Type: application/json" \
    -d '{"spo2": 70, "timestamp": 1700000000}'

# 3. Fake sleep data injection
check_endpoint "Fake sleep data injection (no auth)" \
    -X POST "${BASE_URL}/api/biometric/webhook" \
    -H "Content-Type: application/json" \
    -d '{"sleep_stage": "awake", "sleep_duration_minutes": 0}'

# 4. Read latest biometrics (sensitive health data)
check_endpoint "Read latest biometrics (no auth)" \
    -X GET "${BASE_URL}/api/biometric/latest"

# 5. Read sleep data (sensitive health data)
check_endpoint "Read sleep summary (no auth)" \
    -X GET "${BASE_URL}/api/biometric/sleep"

echo ""
echo "=== Results: PASS=$PASS FAIL=$FAIL SKIP=$SKIP ==="
if [ "$FAIL" -gt 0 ]; then
    echo "STATUS: VULNERABLE ($FAIL issues)"
    exit 1
else
    echo "STATUS: SECURE (or service not running)"
    exit 0
fi
