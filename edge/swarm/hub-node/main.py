"""
SwarmHub firmware for ESP32-S3/C6.

Runs MCPDevice for WiFi/MQTT + SwarmHub for Leaf aggregation.
Supports ESP-NOW and UART transports (configured via config.json).
"""

import time
import json
import sys

sys.path.insert(0, "/lib")
from soms_mcp import MCPDevice
from swarm.hub import SwarmHub
from swarm.transport_espnow import ESPNowTransport
from swarm.transport_uart import UARTTransport


def load_swarm_config():
    try:
        with open("config.json") as f:
            cfg = json.load(f)
        return cfg.get("swarm", {})
    except OSError:
        return {}


def main():
    # MCPDevice handles WiFi, MQTT, heartbeat
    device = MCPDevice()
    swarm_cfg = load_swarm_config()

    hub = SwarmHub(device, wake_chains=swarm_cfg.get("wake_chains", {}))

    # Initialize configured transports
    transport_names = swarm_cfg.get("transports", ["espnow"])

    if "espnow" in transport_names:
        espnow_t = ESPNowTransport(
            mode="hub",
            channel=swarm_cfg.get("espnow_channel", 1),
        )
        espnow_t.init()
        hub.add_transport(espnow_t)
        print("[Hub] ESP-NOW transport ready")

    if "uart" in transport_names:
        uart_cfg = swarm_cfg.get("uart", {})
        uart_t = UARTTransport(
            uart_id=uart_cfg.get("uart_id", 1),
            tx=uart_cfg.get("tx", 17),
            rx=uart_cfg.get("rx", 16),
            baudrate=uart_cfg.get("baudrate", 115200),
        )
        uart_t.init()
        hub.add_transport(uart_t)
        print("[Hub] UART transport ready")

    # Connect WiFi + MQTT
    try:
        device.connect()
    except Exception as e:
        print("Connection failed: %s" % e)
        import machine
        machine.reset()

    print("[Hub] Running — device_id=%s" % device.device_id)

    # Main loop
    while True:
        try:
            device.loop()    # MQTT + heartbeat
            hub.poll()       # Process Leaf messages

            time.sleep(0.1)
        except OSError as e:
            print("Connection error: %s" % e)
            try:
                device.reconnect()
            except Exception:
                import machine
                machine.reset()


if __name__ == "__main__":
    main()
