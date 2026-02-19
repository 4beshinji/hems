"""
UART Leaf firmware for Raspberry Pi Pico (MicroPython).

Reads sensors and sends data to Hub via UART.
No WiFi needed — wired connection to Hub.
"""

import json
import sys
import time

sys.path.insert(0, "/lib")

from machine import Pin, ADC
from swarm.leaf import SwarmLeaf
from swarm.transport_uart import UARTTransport
from swarm.message import CH_TEMPERATURE, CH_HUMIDITY, HW_PICO


# ── Config ───────────────────────────────────────────────────

def load_config():
    try:
        with open("config.json") as f:
            return json.load(f)
    except OSError:
        return {}


# ── Sensor reading (Pico onboard temp + optional external) ──

def read_pico_temp():
    """Read Pico's internal temperature sensor."""
    sensor = ADC(4)  # Internal temp sensor on ADC channel 4
    raw = sensor.read_u16()
    voltage = raw * 3.3 / 65535
    temp_c = 27.0 - (voltage - 0.706) / 0.001721
    return {CH_TEMPERATURE: round(temp_c, 1)}


# ── Main ─────────────────────────────────────────────────────

def main():
    cfg = load_config()

    transport = UARTTransport(
        uart_id=cfg.get("uart_id", 0),
        tx=cfg.get("tx_pin", 0),
        rx=cfg.get("rx_pin", 1),
        baudrate=cfg.get("baudrate", 115200),
    )
    transport.init()

    leaf = SwarmLeaf(
        leaf_id=cfg.get("leaf_id", 10),
        hw_type=HW_PICO,
        transport=transport,
    )
    leaf.add_capability(CH_TEMPERATURE)

    interval = cfg.get("report_interval", 30)
    print("[UART Leaf %d] Starting — interval=%ds" % (leaf.leaf_id, interval))

    leaf.run(
        read_fn=read_pico_temp,
        interval_sec=interval,
        deep_sleep_enabled=False,
    )


if __name__ == "__main__":
    main()
