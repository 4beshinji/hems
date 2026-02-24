#!/usr/bin/env bash
# 全セキュリティPoC を一括実行
# 使い方: bash tests/security/run_all_pocs.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TOTAL_PASS=0
TOTAL_FAIL=0
TOTAL_SKIP=0
FAILED_TESTS=()

run_test() {
    local name="$1"
    local cmd="$2"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Running: $name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if eval "$cmd"; then
        echo "→ $name: PASSED"
        TOTAL_PASS=$((TOTAL_PASS + 1))
    else
        local rc=$?
        if [ $rc -eq 2 ]; then
            echo "→ $name: SKIPPED"
            TOTAL_SKIP=$((TOTAL_SKIP + 1))
        else
            echo "→ $name: FAILED"
            TOTAL_FAIL=$((TOTAL_FAIL + 1))
            FAILED_TESTS+=("$name")
        fi
    fi
}

echo "╔══════════════════════════════════════════════════════╗"
echo "║          HEMS Security PoC Test Suite                ║"
echo "╚══════════════════════════════════════════════════════╝"

# V1: MQTT ACL
run_test "V1: MQTT ACL" \
    "bash '${SCRIPT_DIR}/poc_mqtt_acl.sh'"

# V2: Prompt Injection (publish only, no live verification without running Brain)
run_test "V2: Prompt Injection" \
    "python3 '${SCRIPT_DIR}/poc_prompt_injection.py'"

# V3: Command Bypass (unit test — no services needed)
run_test "V3: Command Bypass" \
    "python3 '${SCRIPT_DIR}/poc_command_bypass.py'"

# V4: Path Traversal (unit test — no services needed)
run_test "V4: Path Traversal" \
    "python3 '${SCRIPT_DIR}/poc_path_traversal.py'"

# V5: Biometric Spoof
run_test "V5: Biometric Spoof" \
    "bash '${SCRIPT_DIR}/poc_biometric_spoof.sh'"

# V6: CORS/CSRF (HTML-based — instructions only)
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "V6: CORS/CSRF — manual test required"
echo "  Open in browser: ${SCRIPT_DIR}/poc_cors_csrf.html"
echo "  Check browser console for FAIL/PASS messages"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# V7: Unauth API
run_test "V7: Unauthenticated API" \
    "bash '${SCRIPT_DIR}/poc_unauth_api.sh'"

# V8: HA params
run_test "V8: HA Bridge Parameters" \
    "python3 '${SCRIPT_DIR}/poc_ha_params.py'"

# Summary
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║                    SUMMARY                           ║"
echo "╠══════════════════════════════════════════════════════╣"
printf "║  Tests PASSED: %-37d ║\n" "$TOTAL_PASS"
printf "║  Tests FAILED: %-37d ║\n" "$TOTAL_FAIL"
printf "║  Tests SKIPPED: %-36d ║\n" "$TOTAL_SKIP"
echo "╚══════════════════════════════════════════════════════╝"

if [ "${#FAILED_TESTS[@]}" -gt 0 ]; then
    echo ""
    echo "Failed tests:"
    for t in "${FAILED_TESTS[@]}"; do
        echo "  - $t"
    done
    echo ""
    echo "STATUS: VULNERABLE — fix the above issues and re-run"
    exit 1
else
    echo ""
    echo "STATUS: ALL TESTS PASSED (or skipped due to services not running)"
    exit 0
fi
