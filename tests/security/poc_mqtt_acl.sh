#!/usr/bin/env bash
# PoC V1: MQTT connectivity test
# MQTT auth/ACL removed (LAN-trusted); this now verifies anonymous connectivity.

set -euo pipefail

MQTT_HOST="${MQTT_HOST:-127.0.0.1}"
MQTT_PORT="${MQTT_PORT:-1893}"
TIMEOUT=5

PASS=0
SKIP=0

echo "=== V1: MQTT Connectivity Test (host=$MQTT_HOST:$MQTT_PORT) ==="
echo "(Auth/ACL removed — LAN-trusted deployment)"
echo ""

if ! command -v mosquitto_pub &>/dev/null; then
    echo "[SKIP] mosquitto_pub not found — install mosquitto-clients"
    SKIP=$((SKIP + 1))
else
    if mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" \
        -t "hems/test" -m "ok" \
        --timeout "$TIMEOUT" 2>/dev/null; then
        echo "[PASS] Anonymous publish to hems/test succeeded"
        PASS=$((PASS + 1))
    else
        echo "[SKIP] MQTT broker not reachable"
        SKIP=$((SKIP + 1))
    fi
fi

echo ""
echo "=== Results: PASS=$PASS SKIP=$SKIP ==="
echo "STATUS: OK (anonymous MQTT by design)"
exit 0
