"""
Virtual in-memory transport for SwarmHub <-> SwarmLeaf communication.
Simulates ESP-NOW / BLE / UART without real hardware.
"""

import logging
import threading
from collections import deque

logger = logging.getLogger(__name__)


class VirtualTransport:
    """Bidirectional in-memory transport between a Hub and its Leaves."""

    def __init__(self, name="virtual", latency_ms=0, loss_rate=0.0):
        self.name = name
        self.latency_ms = latency_ms
        self.loss_rate = loss_rate
        # leaf_id -> queue of bytes (Leaf->Hub direction)
        self._to_hub = deque()
        # leaf_id -> queue of bytes (Hub->Leaf direction)
        self._to_leaf = {}
        self._lock = threading.Lock()

    def register_leaf(self, leaf_id):
        """Register a leaf so the Hub can send to it."""
        with self._lock:
            if leaf_id not in self._to_leaf:
                self._to_leaf[leaf_id] = deque()

    def send_to_hub(self, leaf_id, data):
        """Leaf sends data to Hub."""
        if self.loss_rate > 0:
            import random
            if random.random() < self.loss_rate:
                logger.debug(f"[{self.name}] Packet from leaf {leaf_id} dropped (simulated loss)")
                return
        with self._lock:
            self._to_hub.append((leaf_id, data))

    def send_to_leaf(self, leaf_id, data):
        """Hub sends data to a specific Leaf."""
        if self.loss_rate > 0:
            import random
            if random.random() < self.loss_rate:
                logger.debug(f"[{self.name}] Packet to leaf {leaf_id} dropped (simulated loss)")
                return
        with self._lock:
            q = self._to_leaf.get(leaf_id)
            if q is not None:
                q.append(data)
            else:
                logger.warning(f"[{self.name}] Unknown leaf {leaf_id}")

    def receive_from_leaves(self):
        """Hub polls for all pending Leaf->Hub messages. Returns list of (leaf_id, data)."""
        messages = []
        with self._lock:
            while self._to_hub:
                messages.append(self._to_hub.popleft())
        return messages

    def receive_from_hub(self, leaf_id):
        """Leaf polls for Hub->Leaf messages. Returns list of data bytes."""
        messages = []
        with self._lock:
            q = self._to_leaf.get(leaf_id)
            if q:
                while q:
                    messages.append(q.popleft())
        return messages
