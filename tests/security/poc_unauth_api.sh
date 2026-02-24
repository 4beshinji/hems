#!/usr/bin/env bash
# PoC V7: 認証なし API テスト
# backend の全エンドポイントが認証なしでアクセスできるか確認

set -euo pipefail

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8010}"
TIMEOUT=5
BASE_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"

PASS=0
FAIL=0
SKIP=0

check_endpoint() {
    local description="$1"
    local method="${2:-GET}"
    local path="$3"
    local data="${4:-}"
    local status

    local curl_args=(-s -o /dev/null -w "%{http_code}" --connect-timeout "$TIMEOUT" -X "$method")
    if [ -n "$data" ]; then
        curl_args+=(-H "Content-Type: application/json" -d "$data")
    fi

    status=$(curl "${curl_args[@]}" "${BASE_URL}${path}" 2>/dev/null || echo "000")

    case "$status" in
        000)
            echo "[SKIP] $description — service not reachable"
            SKIP=$((SKIP + 1))
            ;;
        200|201)
            echo "[FAIL] $description — accessible without auth (HTTP $status)"
            FAIL=$((FAIL + 1))
            ;;
        401|403)
            echo "[PASS] $description — rejected (HTTP $status)"
            PASS=$((PASS + 1))
            ;;
        404)
            echo "[INFO] $description — not found (HTTP $status)"
            ;;
        *)
            echo "[INFO] $description — HTTP $status"
            SKIP=$((SKIP + 1))
            ;;
    esac
}

echo "=== V7: Unauthenticated API Test (${BASE_URL}) ==="
echo ""

# Read endpoints
check_endpoint "GET /tasks/ (list tasks)"        GET "/tasks/"
check_endpoint "GET /tasks/stats"               GET "/tasks/stats"
check_endpoint "GET /users/"                    GET "/users/"
check_endpoint "GET /zones/"                    GET "/zones/"
check_endpoint "GET /voice-events/"             GET "/voice-events/"
check_endpoint "GET /points/"                   GET "/points/"

# Write endpoints (high impact)
check_endpoint "POST /tasks/ (create task)" POST "/tasks/" \
    '{"title":"Injected Task","xp_reward":500,"urgency":4}'
check_endpoint "POST /users/ (create user)" POST "/users/" \
    '{"username":"hacker","display_name":"Hacker"}'

# Home/device control endpoints
check_endpoint "GET /home/devices"      GET "/home/devices"
check_endpoint "POST /home/control"     POST "/home/control" \
    '{"entity_id":"light.bedroom","service":"light/turn_off","data":{}}'

# PC control
check_endpoint "GET /pc/status"         GET "/pc/status"
check_endpoint "POST /pc/command"       POST "/pc/command" \
    '{"command":"id"}'

# Biometric (sensitive health data)
check_endpoint "GET /biometric/latest"  GET "/biometric/latest"
check_endpoint "GET /biometric/sleep"   GET "/biometric/sleep"

# Knowledge
check_endpoint "POST /knowledge/search" POST "/knowledge/search" \
    '{"query":"secret"}'

echo ""
echo "=== Results: PASS=$PASS FAIL=$FAIL SKIP=$SKIP ==="
if [ "$FAIL" -gt 0 ]; then
    echo "STATUS: VULNERABLE ($FAIL endpoints accessible without auth)"
    exit 1
else
    echo "STATUS: SECURE (or service not running)"
    exit 0
fi
