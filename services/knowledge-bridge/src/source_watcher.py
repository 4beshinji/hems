"""
Source watcher — monitors multiple source directories for file changes via watchdog.
Debounces events and triggers index update + MQTT publish.
"""

import asyncio
import time
from pathlib import Path

from document_index import DocumentIndex
from loguru import logger
from mqtt_publisher import MQTTPublisher
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


class _SourceEventHandler(FileSystemEventHandler):
    """Collects file change events with debouncing for a single source."""

    def __init__(
        self,
        source_name: str,
        source_path: str,
        extensions: set[str],
        exclude_patterns: list[str],
        debounce_seconds: float,
    ):
        self.source_name = source_name
        self.source_path = Path(source_path)
        self.extensions = extensions
        self.exclude_patterns = exclude_patterns
        self.debounce = debounce_seconds
        self._pending: dict[str, tuple[str, float]] = {}  # rel_path → (action, ts)

    def _handle(self, event: FileSystemEvent, action: str):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in self.extensions:
            return
        try:
            rel = str(path.relative_to(self.source_path))
        except ValueError:
            return
        # Skip hidden directories
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
            if dest.suffix.lower() in self.extensions:
                try:
                    rel = str(dest.relative_to(self.source_path))
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


class SourceWatcher:
    """Watches multiple source directories, updates index and publishes MQTT events."""

    def __init__(self, doc_index: DocumentIndex, mqtt_pub: MQTTPublisher, debounce: float = 3.0):
        self.index = doc_index
        self.mqtt = mqtt_pub
        self.debounce = debounce
        self._handlers: dict[str, _SourceEventHandler] = {}  # source_name → handler
        self._observer: Observer | None = None

    def add_source(self, source_name: str, source_path: str, extensions: list[str], exclude_patterns: list[str]):
        """Register a source directory for watching."""
        path = Path(source_path)
        if not path.exists():
            logger.warning(f"Watcher: source '{source_name}' path not found: {source_path}")
            return

        handler = _SourceEventHandler(
            source_name,
            source_path,
            set(extensions),
            exclude_patterns,
            self.debounce,
        )
        self._handlers[source_name] = handler

    def start(self):
        """Start filesystem observers for all registered sources."""
        self._observer = Observer()
        for name, handler in self._handlers.items():
            path_str = str(handler.source_path)
            self._observer.schedule(handler, path_str, recursive=True)
            logger.info(f"Watcher started for source '{name}': {path_str}")
        if self._handlers:
            self._observer.start()

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)

    async def process_loop(self):
        """Periodically drain debounced events and update index."""
        while True:
            await asyncio.sleep(1)
            for source_name, handler in self._handlers.items():
                ready = handler.drain_ready()
                for rel_path, action in ready:
                    try:
                        if action == "deleted":
                            self.index.remove_file(source_name, rel_path)
                            logger.debug(f"Document removed: {source_name}:{rel_path}")
                        else:
                            await self.index.reindex_file_with_vector(source_name, rel_path)
                            logger.debug(f"Document reindexed: {source_name}:{rel_path}")

                        # MQTT payload
                        doc_key = f"{source_name}:{rel_path}"
                        entry = self.index.documents.get(doc_key)
                        payload = {
                            "source": source_name,
                            "path": rel_path,
                            "action": action,
                            "title": entry.title if entry else Path(rel_path).stem,
                            "doc_type": entry.doc_type if entry else "unknown",
                        }
                        self.mqtt.publish("hems/personal/knowledge/changed", payload)
                    except Exception as e:
                        logger.warning(f"Watcher process error for {source_name}:{rel_path}: {e}")

    async def publish_stats_loop(self, interval: int = 60):
        """Periodically publish source stats to MQTT."""
        while True:
            await asyncio.sleep(interval)
            stats = self.index.get_source_stats()
            payload = {
                "sources": stats,
                "total_docs": self.index.get_total_docs(),
            }
            self.mqtt.publish("hems/personal/knowledge/stats", payload)
