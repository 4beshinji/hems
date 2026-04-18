#!/usr/bin/env bash
# Reset all registered devices in the Device Registry.
# Usage: bash scripts/reset_devices.sh [backend_url]

BACKEND=${1:-http://localhost:8010}

echo "Deleting all devices from $BACKEND/devices/all ..."
result=$(curl -s -X DELETE "$BACKEND/devices/all")
echo "$result"

echo ""
echo "Device registry cleared. Z2M bridge/devices will re-annotate on next MQTT publish."
echo "To force re-annotation: mosquitto_pub -h localhost -p 1893 -t zigbee2mqtt/bridge/request/devices -m ''"
