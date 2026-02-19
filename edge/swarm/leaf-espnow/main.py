"""
ESP-NOW Leaf firmware for ESP32-C3/C6.

Boot → read sensors → ESP-NOW send → deep sleep.
No WiFi AP connection needed. Battery-optimized.
"""

import json
import sys

sys.path.insert(0, "/lib")

from machine import Pin, ADC
from swarm.leaf import SwarmLeaf
from swarm.transport_espnow import ESPNowTransport
from swarm.message import CH_TEMPERATURE, CH_HUMIDITY, HW_ESP32

# ── Config ───────────────────────────────────────────────────

def load_config():
    try:
        with open("config.json") as f:
            return json.load(f)
    except OSError:
        return {}


def parse_mac(mac_str):
    """Parse 'AA:BB:CC:DD:EE:FF' to bytes."""
    return bytes(int(x, 16) for x in mac_str.split(":"))


# ── Sensor reading (example: onboard temp + external DHT22) ─

def make_reader(sensor_types):
    """Create a sensor read function based on configured sensor list."""
    readers = {}

    if "temperature" in sensor_types or "humidity" in sensor_types:
        try:
            import dht
            _dht = dht.DHT22(Pin(4))

            def read_dht():
                _dht.measure()
                data = {}
                if "temperature" in sensor_types:
                    data[CH_TEMPERATURE] = _dht.temperature()
                if "humidity" in sensor_types:
                    data[CH_HUMIDITY] = _dht.humidity()
                return data

            readers["dht"] = read_dht
        except Exception as e:
            print("DHT init failed: %s" % e)

    def read_all():
        result = {}
        for name, fn in readers.items():
            try:
                result.update(fn())
            except Exception as e:
                print("Sensor %s error: %s" % (name, e))
        return result

    return read_all


def read_battery():
    """Read battery voltage via ADC (voltage divider on GPIO0)."""
    try:
        adc = ADC(Pin(0), atten=ADC.ATTN_11DB)
        raw = adc.read_uv() / 1000  # millivolts
        # Assuming 2:1 voltage divider
        return int(raw * 2)
    except Exception:
        return 0


# ── Main ─────────────────────────────────────────────────────

def main():
    cfg = load_config()

    hub_mac = parse_mac(cfg.get("hub_mac", "FF:FF:FF:FF:FF:FF"))
    channel = cfg.get("espnow_channel", 1)

    transport = ESPNowTransport(mode="leaf", hub_mac=hub_mac, channel=channel)
    transport.init()

    leaf = SwarmLeaf(
        leaf_id=cfg.get("leaf_id", 1),
        hw_type=cfg.get("hw_type", HW_ESP32),
        transport=transport,
    )

    sensor_types = cfg.get("sensors", ["temperature", "humidity"])
    for s in sensor_types:
        from swarm.message import CHANNEL_BY_NAME
        cap = CHANNEL_BY_NAME.get(s)
        if cap is not None:
            leaf.add_capability(cap)

    read_fn = make_reader(sensor_types)
    interval = cfg.get("report_interval", 30)
    use_deepsleep = cfg.get("deep_sleep", True)

    print("[Leaf %d] Starting — interval=%ds deepsleep=%s" % (
        leaf.leaf_id, interval, use_deepsleep))

    leaf.run(
        read_fn=read_fn,
        interval_sec=interval,
        deep_sleep_enabled=use_deepsleep,
        battery_fn=read_battery,
    )


if __name__ == "__main__":
    main()
