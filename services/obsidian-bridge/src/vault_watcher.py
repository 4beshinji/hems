"""
Vault watcher — monitors Obsidian vault for file changes via watchdog.
Debounces events and triggers MQTT publish + index update.
"""
import asyncio
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from loguru import logger

from vault_index import VaultIndex
from mqtt_publisher import MQTTPublisher


class _VaultEventHandler(FileSystemEventHandler):
    """Collects file change events with debouncing."""

    def __init__(self, vault_path: str, debounce_seconds: float):
        self.vault_path = Path(vault_path)
        self.debounce = debounce_seconds
        self._pending: dict[str, tuple[str, float]] = {}  # rel_path → (action, timestamp)
        self._lock = asyncio.Lock()

    def _handle(self, event: FileSystemEvent, action: str):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if not path.suffix == ".md":
            return
        # Skip hidden directories
        try:
            rel = str(path.relative_to(self.vault_path))
        except ValueError:
            return
        if any(part.startswith(".") for part in Path(rel).parts):
            return
        self._pending[rel] = (action, time.time())

    def on_created(self, event):
        self._handle(event, "created")

    def on_modified(self, event):
        self._handle(event, "modified")

    def on_deleted(self, event):
        self._handle(event, "deleted")

    def on_moved(self, event):
        self._handle(event, "deleted")
        if hasattr(event, "dest_path"):
            dest = Path(event.dest_path)
            if dest.suffix == ".md":
                try:
                    rel = str(dest.relative_to(self.vault_path))
                    if not any(part.startswith(".") for part in Path(rel).parts):
                        self._pending[rel] = ("created", time.time())
                except ValueError:
                    pass

    def drain_ready(self) -> list[tuple[str, str]]:
        """Return debounced events that are ready to process."""
        now = time.time()
        ready = []
        still_pending = {}
        for rel_path, (action, ts) in self._pending.items():
            if now - ts >= self.debounce:
                ready.append((rel_path, action))
            else:
                still_pending[rel_path] = (action, ts)
        self._pending = still_pending
        return ready


class VaultWatcher:
    """Watches vault directory, updates index and publishes MQTT events."""

    def __init__(self, vault_index: VaultIndex, mqtt_pub: MQTTPublisher,
                 debounce: float = 2.0):
        self.index = vault_index
        self.mqtt = mqtt_pub
        self._handler = _VaultEventHandler(vault_index.vault_path, debounce)
        self._observer: Observer | None = None

    def start(self):
        """Start the filesystem observer."""
        vault_str = str(self.index.vault_path)
        self._observer = Observer()
        self._observer.schedule(self._handler, vault_str, recursive=True)
        self._observer.start()
        logger.info(f"Vault watcher started: {vault_str}")

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)

    async def process_loop(self):
        """Periodically drain debounced events and update index."""
        while True:
            await asyncio.sleep(1)
            ready = self._handler.drain_ready()
            for rel_path, action in ready:
                try:
                    if action == "deleted":
                        self.index.remove_file(rel_path)
                        logger.debug(f"Note removed from index: {rel_path}")
                    else:
                        self.index.reindex_file(rel_path)
                        logger.debug(f"Note reindexed: {rel_path}")

                    # Build MQTT payload
                    entry = self.index.notes.get(rel_path)
                    payload = {
                        "path": rel_path,
                        "action": action,
                        "title": entry.title if entry else Path(rel_path).stem,
                        "tags": entry.tags if entry else [],
                    }
                    self.mqtt.publish("hems/personal/notes/changed", payload)
                except Exception as e:
                    logger.warning(f"Watcher process error for {rel_path}: {e}")

    async def publish_stats_loop(self, interval: int = 60):
        """Periodically publish vault stats to MQTT."""
        while True:
            await asyncio.sleep(interval)
            stats = self.index.get_stats()
            self.mqtt.publish("hems/personal/notes/stats", stats)
