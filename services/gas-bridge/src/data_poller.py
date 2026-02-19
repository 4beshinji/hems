"""
Data poller — fetches each data type from GAS on configured intervals and publishes to MQTT.
"""
import asyncio
import time
from loguru import logger

from gas_client import GASClient
from mqtt_publisher import MQTTPublisher
import config


class DataPoller:
    """Manages periodic polling of GAS data and MQTT publishing."""

    def __init__(self, gas_client: GASClient, mqtt_pub: MQTTPublisher):
        self.gas = gas_client
        self.mqtt = mqtt_pub

        # Cached data for REST API
        self.calendar_data: dict | None = None
        self.free_slots_data: dict | None = None
        self.tasks_data: dict | None = None
        self.tasks_due_data: dict | None = None
        self.gmail_data: dict | None = None
        self.gmail_recent_data: dict | None = None
        self.sheets_data: dict[str, dict] = {}
        self.drive_data: dict | None = None

        self._last_update: dict[str, float] = {}
        self._connected = False

    def _parse_sheets_config(self) -> list[dict]:
        """Parse HEMS_GAS_SHEETS env var into list of sheet configs."""
        if not config.SHEETS_CONFIG:
            return []
        sheets = []
        for entry in config.SHEETS_CONFIG.split(","):
            parts = entry.strip().split(":")
            if len(parts) >= 2:
                sheets.append({
                    "name": parts[0],
                    "id": parts[1],
                    "sheet": parts[2] if len(parts) >= 3 else "",
                    "range": parts[3] if len(parts) >= 4 else "",
                })
        return sheets

    async def poll_calendar(self):
        """Poll calendar data (upcoming events + free slots)."""
        while True:
            try:
                upcoming = await self.gas.fetch("calendar_upcoming", hours="24")
                if upcoming:
                    self.calendar_data = upcoming
                    self._last_update["calendar"] = time.time()
                    self.mqtt.publish("hems/gas/calendar/upcoming", upcoming)

                free_slots = await self.gas.fetch("calendar_free_slots", hours="12")
                if free_slots:
                    self.free_slots_data = free_slots
                    self.mqtt.publish("hems/gas/calendar/free_slots", free_slots)

                self._update_bridge_status()
            except Exception as e:
                logger.error(f"Calendar poll error: {e}")

            await asyncio.sleep(config.CALENDAR_INTERVAL)

    async def poll_tasks(self):
        """Poll Google Tasks data."""
        while True:
            try:
                all_tasks = await self.gas.fetch("tasks_list")
                if all_tasks:
                    self.tasks_data = all_tasks
                    self._last_update["tasks"] = time.time()
                    self.mqtt.publish("hems/gas/tasks/all", all_tasks)

                due_today = await self.gas.fetch("tasks_due_today")
                if due_today:
                    self.tasks_due_data = due_today
                    self.mqtt.publish("hems/gas/tasks/due_today", due_today)

                self._update_bridge_status()
            except Exception as e:
                logger.error(f"Tasks poll error: {e}")

            await asyncio.sleep(config.TASKS_INTERVAL)

    async def poll_gmail(self):
        """Poll Gmail summary and recent threads."""
        while True:
            try:
                summary = await self.gas.fetch("gmail_summary")
                if summary:
                    self.gmail_data = summary
                    self._last_update["gmail"] = time.time()
                    self.mqtt.publish("hems/gas/gmail/summary", summary)

                recent = await self.gas.fetch("gmail_recent", count="10")
                if recent:
                    self.gmail_recent_data = recent
                    self.mqtt.publish("hems/gas/gmail/recent", recent)

                self._update_bridge_status()
            except Exception as e:
                logger.error(f"Gmail poll error: {e}")

            await asyncio.sleep(config.GMAIL_INTERVAL)

    async def poll_sheets(self):
        """Poll configured Google Sheets."""
        sheets_cfg = self._parse_sheets_config()
        if not sheets_cfg:
            return  # No sheets configured, exit loop

        while True:
            try:
                for sheet in sheets_cfg:
                    params = {"id": sheet["id"]}
                    if sheet["sheet"]:
                        params["sheet"] = sheet["sheet"]
                    if sheet["range"]:
                        params["range"] = sheet["range"]

                    data = await self.gas.fetch("sheets_read", **params)
                    if data:
                        data["_name"] = sheet["name"]
                        data["_last_update"] = time.time()
                        self.sheets_data[sheet["name"]] = data
                        self.mqtt.publish(f"hems/gas/sheets/{sheet['name']}", data)

                self._last_update["sheets"] = time.time()
                self._update_bridge_status()
            except Exception as e:
                logger.error(f"Sheets poll error: {e}")

            await asyncio.sleep(config.SHEETS_INTERVAL)

    async def poll_drive(self):
        """Poll Google Drive recent files."""
        while True:
            try:
                recent = await self.gas.fetch("drive_recent", count="20")
                if recent:
                    self.drive_data = recent
                    self._last_update["drive"] = time.time()
                    self.mqtt.publish("hems/gas/drive/recent", recent)

                self._update_bridge_status()
            except Exception as e:
                logger.error(f"Drive poll error: {e}")

            await asyncio.sleep(config.DRIVE_INTERVAL)

    def _update_bridge_status(self):
        """Publish bridge connection status."""
        self._connected = True
        self.mqtt.publish("hems/gas/bridge/status", {
            "connected": True,
            "last_updates": self._last_update,
            "timestamp": time.time(),
        })

    def get_status(self) -> dict:
        """Get current status for REST API."""
        return {
            "connected": self._connected,
            "last_updates": self._last_update,
            "calendar_events": len((self.calendar_data or {}).get("events", [])),
            "tasks_due_today": sum(
                len(tl.get("tasks", []))
                for tl in (self.tasks_due_data or {}).get("taskLists", [])
            ),
            "gmail_inbox_unread": (self.gmail_data or {}).get("labels", {}).get("INBOX", {}).get("unread", 0),
            "sheets_monitored": len(self.sheets_data),
            "drive_recent_files": len((self.drive_data or {}).get("files", [])),
        }
