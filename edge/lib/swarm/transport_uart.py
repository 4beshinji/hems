"""
UART transport for SwarmHub and SwarmLeaf.

Provides framed serial communication between Hub and Leaf over UART.
Uses the swarm message magic byte (0x53) for frame synchronization.

Suitable for Pi Pico, ATtiny (via software serial), and other
UART-capable microcontrollers connected by wire.
"""

try:
    from machine import UART, Pin
except ImportError:
    UART = None
    Pin = None

from swarm.message import MAGIC, HEADER_SIZE, CHECKSUM_SIZE


class UARTTransport:
    """
    UART-based transport with frame synchronization.

    Hub usage:
        transport = UARTTransport(uart_id=1, tx=17, rx=16)
        transport.init()

    Leaf usage:
        transport = UARTTransport(uart_id=0, tx=0, rx=1)
        transport.init()
    """

    def __init__(self, uart_id=1, tx=17, rx=16, baudrate=115200):
        self.uart_id = uart_id
        self.tx_pin = tx
        self.rx_pin = rx
        self.baudrate = baudrate
        self._uart = None
        self._rx_buf = bytearray()

    def init(self):
        """Initialize UART hardware."""
        if UART is None:
            raise RuntimeError("UART not available on this platform")
        self._uart = UART(
            self.uart_id, baudrate=self.baudrate,
            tx=Pin(self.tx_pin), rx=Pin(self.rx_pin),
            bits=8, parity=None, stop=1,
        )

    def send(self, addr, data):
        """
        Send a frame over UART. addr is ignored (point-to-point link).
        """
        if self._uart is None:
            return
        self._uart.write(data)

    def receive(self):
        """
        Non-blocking receive. Attempts to parse a complete frame from
        the UART buffer. Returns (None, data) or None.
        (addr is always None for UART — point-to-point)
        """
        if self._uart is None:
            return None

        # Read available bytes into buffer
        avail = self._uart.any()
        if avail > 0:
            chunk = self._uart.read(avail)
            if chunk:
                self._rx_buf.extend(chunk)

        return self._try_parse_frame()

    def _try_parse_frame(self):
        """Try to extract a complete frame from _rx_buf."""
        # Find magic byte
        while len(self._rx_buf) > 0 and self._rx_buf[0] != MAGIC:
            self._rx_buf.pop(0)

        if len(self._rx_buf) < HEADER_SIZE + CHECKSUM_SIZE:
            return None

        # We need to determine payload length.
        # For SENSOR_REPORT (0x01): 1 byte N + N * 5 bytes
        # For HEARTBEAT (0x02): 6 bytes
        # For REGISTER (0x04): 2 + N bytes
        # For COMMAND (0x80): 2 + arg_len bytes
        # For ACK (0xFE), WAKE (0xFF): 0 bytes
        #
        # Strategy: try parsing with increasing lengths until checksum matches
        # (simple and robust for low-bandwidth UART)
        from swarm.message import _xor_checksum

        for frame_len in range(HEADER_SIZE + CHECKSUM_SIZE, len(self._rx_buf) + 1):
            candidate = bytes(self._rx_buf[:frame_len])
            cs = _xor_checksum(candidate[:-1])
            if cs == candidate[-1]:
                # Valid frame found
                del self._rx_buf[:frame_len]
                return (None, candidate)

        # No valid frame yet — wait for more data
        # Prevent buffer from growing unbounded
        if len(self._rx_buf) > 512:
            self._rx_buf = self._rx_buf[-256:]
        return None

    def close(self):
        if self._uart:
            self._uart.deinit()
            self._uart = None
