#!/bin/sh
# HEMS z2m wrapper — applies a one-line runtime patch to zigbee-herdsman to bypass
# the strict configuration-adapter mismatch check when only the adapter's
# *preconfigured* network key slot differs from config (active/alternate keys still
# match). This situation arises when a second z2m daemon (e.g. a parallel SOMS
# instance) momentarily contended for the USB coordinator and rewrote the
# preconfigured slot with its default key. Existing paired devices keep working
# because they use the active key. New joins also use the active key during TCKEY
# transport, so device pairing remains functional.
#
# The patch flips a single boolean in herdsman's manager.js so the existing
# `forceStartWithInconsistentAdapterConfiguration` branch is always taken.
# Idempotent — safe to run on every container start.
#
# Long-term fix: rewrite the chip's PRECFGKEY NV slot with the correct key, then
# remove this wrapper.
set -e

MGR_GLOB="/app/node_modules/.pnpm/zigbee-herdsman@*/node_modules/zigbee-herdsman/dist/adapter/z-stack/adapter/manager.js"
for f in $MGR_GLOB; do
    if [ -f "$f" ]; then
        sed -i 's|this\.options\.adapterOptions\.forceStartWithInconsistentAdapterConfiguration|true|g' "$f"
        echo "[hems] patched $f to force-start despite preconfigured-key mismatch"
    fi
done

# Defer to the official entrypoint behavior.
if [ -n "$ZIGBEE2MQTT_DATA" ]; then
    DATA="$ZIGBEE2MQTT_DATA"
else
    DATA="/app/data"
fi
echo "Using '$DATA' as data directory"
exec /sbin/tini -- node index.js
