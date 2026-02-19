"""
ESP-NOW transport for SwarmHub and SwarmLeaf.

ESP-NOW runs on top of WiFi hardware but doesn't require an AP connection,
making it ideal for battery-powered devices. Max frame size: 250 bytes.

Hub mode: receives from any peer (broadcast), sends to specific MAC.
Leaf mode: sends to a single Hub MAC address.
"""

try:
    import network
    import espnow
except ImportError:
    network = None
    espnow = None


class ESPNowTransport:
    """
    ESP-NOW transport layer.

    Hub usage:
        transport = ESPNowTransport(mode="hub")
        transport.init()

    Leaf usage:
        transport = ESPNowTransport(mode="leaf", hub_mac=b'\\xaa...')
        transport.init()
    """

    def __init__(self, mode="hub", hub_mac=None, channel=1):
        """
        mode: "hub" (receive from any) or "leaf" (send to hub_mac)
        hub_mac: bytes MAC address of Hub (leaf mode only)
        channel: WiFi channel (must match between Hub and Leaf)
        """
        self.mode = mode
        self.hub_mac = hub_mac
        self.channel = channel
        self._esp = None
        self._sta = None

    def init(self):
        """Initialize ESP-NOW. Must be called after boot."""
        if network is None:
            raise RuntimeError("ESP-NOW not available on this platform")

        self._sta = network.WLAN(network.STA_IF)
        self._sta.active(True)
        # ESP-NOW works alongside WiFi STA — no need to disconnect
        if hasattr(self._sta, "config"):
            self._sta.config(channel=self.channel)

        self._esp = espnow.ESPNow()
        self._esp.active(True)

        if self.mode == "leaf" and self.hub_mac:
            self._esp.add_peer(self.hub_mac)

        # Hub accepts broadcast peers automatically

    def send(self, addr, data):
        """
        Send data to a peer.
        Hub: addr = MAC of target leaf.
        Leaf: addr is ignored (always sends to hub_mac).
        """
        if self._esp is None:
            return
        if self.mode == "leaf":
            self._esp.send(self.hub_mac, data)
        else:
            # Hub sending to a specific leaf
            try:
                self._esp.add_peer(addr)
            except Exception:
                pass  # Already added
            self._esp.send(addr, data)

    def receive(self):
        """
        Non-blocking receive.
        Returns (addr, data) or None if no message available.
        addr is a bytes MAC address.
        """
        if self._esp is None:
            return None
        host, msg = self._esp.recv(0)  # Non-blocking (0 ms timeout)
        if msg is None:
            return None
        return (host, msg)

    def close(self):
        if self._esp:
            self._esp.active(False)
            self._esp = None
