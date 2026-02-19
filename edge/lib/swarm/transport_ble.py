"""
BLE transport stub for future nRF54L15 / ESP32 BLE Leaf devices.

This is a placeholder — BLE implementation depends heavily on the
target platform (Zephyr for nRF, aioble/ubluetooth for ESP32).
The interface matches other transports so it can be plugged into SwarmHub.
"""


class BLETransport:
    """
    BLE transport (stub).

    Future implementation will use BLE advertising for Leaf->Hub data
    and BLE GATT write for Hub->Leaf commands.
    """

    def __init__(self):
        self._initialized = False

    def init(self):
        print("[BLE] Transport stub — not yet implemented")
        self._initialized = True

    def send(self, addr, data):
        """Send data to a BLE peripheral (not yet implemented)."""
        pass

    def receive(self):
        """Receive data from BLE peripherals (not yet implemented)."""
        return None

    def close(self):
        self._initialized = False
