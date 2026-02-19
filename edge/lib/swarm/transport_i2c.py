"""
I2C transport for SwarmHub (master) and SwarmLeaf (slave).

Hub acts as I2C master, polling slave devices at known addresses.
Each Leaf has a unique I2C address (0x10–0x7E range).
Suitable for ATtiny and other I2C-capable microcontrollers on a shared bus.

Limitations:
- Master-initiated only (Hub polls Leaf)
- Max transfer ~32 bytes per transaction on many I2C implementations
- For larger payloads, the Hub reads in chunks
"""

try:
    from machine import I2C, Pin
except ImportError:
    I2C = None
    Pin = None

from swarm.message import MAGIC, HEADER_SIZE, CHECKSUM_SIZE


class I2CMasterTransport:
    """
    I2C master transport for Hub.

    The Hub periodically polls each registered leaf address.
    Leaf devices prepare their latest frame in a buffer and respond
    when the master reads from them.

    Usage:
        transport = I2CMasterTransport(scl=22, sda=21)
        transport.init()
        transport.add_leaf_addr(0x10)
    """

    def __init__(self, i2c_id=0, scl=22, sda=21, freq=100000):
        self.i2c_id = i2c_id
        self.scl_pin = scl
        self.sda_pin = sda
        self.freq = freq
        self._i2c = None
        self._leaf_addrs = []  # list of (i2c_addr, leaf_id) tuples

    def init(self):
        if I2C is None:
            raise RuntimeError("I2C not available on this platform")
        self._i2c = I2C(
            self.i2c_id,
            scl=Pin(self.scl_pin),
            sda=Pin(self.sda_pin),
            freq=self.freq,
        )

    def add_leaf_addr(self, i2c_addr, leaf_id=None):
        """Register an I2C address to poll."""
        self._leaf_addrs.append((i2c_addr, leaf_id or i2c_addr))

    def send(self, addr, data):
        """Send data to a leaf at I2C address."""
        if self._i2c is None:
            return
        try:
            self._i2c.writeto(addr, data)
        except OSError:
            pass  # Device not responding

    def receive(self):
        """
        Poll all registered leaf addresses. Returns (addr, data) for the
        first leaf that has data, or None.
        """
        if self._i2c is None:
            return None
        for i2c_addr, _leaf_id in self._leaf_addrs:
            try:
                # Read up to 64 bytes (covers max swarm frame)
                buf = self._i2c.readfrom(i2c_addr, 64)
                if buf and buf[0] == MAGIC:
                    # Trim trailing zeros (padding)
                    end = len(buf)
                    while end > 0 and buf[end - 1] == 0:
                        end -= 1
                    if end >= HEADER_SIZE + CHECKSUM_SIZE:
                        return (i2c_addr, bytes(buf[:end]))
            except OSError:
                pass  # Device not responding or no data
        return None

    def scan(self):
        """Scan I2C bus for devices. Returns list of addresses."""
        if self._i2c is None:
            return []
        return self._i2c.scan()

    def close(self):
        pass  # I2C doesn't need explicit close in MicroPython
