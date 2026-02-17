"""
Service Checker — monitors external service status (Gmail IMAP, GitHub REST, browser scraping).
Publishes to hems/services/{name}/status via MQTT.
"""
import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from loguru import logger


@dataclass
class ServiceStatus:
    name: str = ""
    available: bool = True
    unread_count: int = 0
    summary: str = ""
    details: dict = field(default_factory=dict)
    last_check: float = 0
    error: str | None = None


class BaseChecker(ABC):
    """Abstract base for service checkers."""

    def __init__(self, name: str, interval: int = 300):
        self.name = name
        self.interval = interval
        self._last_status: ServiceStatus | None = None

    @abstractmethod
    async def check(self) -> ServiceStatus:
        ...

    @property
    def last_status(self) -> ServiceStatus | None:
        return self._last_status


class GmailChecker(BaseChecker):
    """Check Gmail unread count via IMAP UNSEEN search."""

    def __init__(self, email: str, app_password: str, interval: int = 300):
        super().__init__("gmail", interval)
        self.email = email
        self.app_password = app_password

    async def check(self) -> ServiceStatus:
        try:
            import aioimaplib
            imap = aioimaplib.IMAP4_SSL("imap.gmail.com")
            await imap.wait_hello_from_server()
            await imap.login(self.email, self.app_password)
            await imap.select("INBOX")
            _, data = await imap.search("UNSEEN")
            unseen_ids = data[0].split() if data and data[0] else []
            count = len(unseen_ids)
            await imap.logout()

            summary = f"未読メール: {count}通" if count > 0 else "未読なし"
            status = ServiceStatus(
                name=self.name, available=True, unread_count=count,
                summary=summary, last_check=time.time(),
            )
            self._last_status = status
            return status
        except Exception as e:
            logger.warning(f"Gmail check failed: {e}")
            status = ServiceStatus(
                name=self.name, available=False,
                summary="Gmail接続エラー", last_check=time.time(),
                error=str(e)[:200],
            )
            self._last_status = status
            return status


class GitHubChecker(BaseChecker):
    """Check GitHub unread notification count via REST API."""

    def __init__(self, token: str, interval: int = 300):
        super().__init__("github", interval)
        self.token = token

    async def check(self) -> ServiceStatus:
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.github.com/notifications",
                    headers=headers, timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        raise Exception(f"GitHub API {resp.status}")
                    notifications = await resp.json()
                    count = len(notifications)

            summary = f"GitHub通知: {count}件" if count > 0 else "通知なし"
            status = ServiceStatus(
                name=self.name, available=True, unread_count=count,
                summary=summary, last_check=time.time(),
                details={"types": _count_github_types(notifications)},
            )
            self._last_status = status
            return status
        except Exception as e:
            logger.warning(f"GitHub check failed: {e}")
            status = ServiceStatus(
                name=self.name, available=False,
                summary="GitHub接続エラー", last_check=time.time(),
                error=str(e)[:200],
            )
            self._last_status = status
            return status


def _count_github_types(notifications: list) -> dict:
    types: dict[str, int] = {}
    for n in notifications:
        reason = n.get("reason", "unknown")
        types[reason] = types.get(reason, 0) + 1
    return types


class BrowserChecker(BaseChecker):
    """Check service status via browser JS evaluation (requires OpenClaw)."""

    def __init__(self, name: str, url: str, js_script: str,
                 oc_client, interval: int = 300, browser_lock: asyncio.Lock | None = None):
        super().__init__(name, interval)
        self.url = url
        self.js_script = js_script
        self.oc_client = oc_client
        self._lock = browser_lock or asyncio.Lock()

    async def check(self) -> ServiceStatus:
        async with self._lock:
            try:
                if not self.oc_client.connected:
                    raise Exception("OpenClaw not connected")
                await self.oc_client.canvas_navigate(self.url)
                await asyncio.sleep(3)  # wait for page load
                result = await self.oc_client.canvas_eval(self.js_script)
                data = json.loads(result) if isinstance(result, str) else result

                count = int(data.get("unread_count", 0))
                summary = data.get("summary", f"{self.name}: {count}件")
                status = ServiceStatus(
                    name=self.name, available=True, unread_count=count,
                    summary=summary, last_check=time.time(),
                    details=data.get("details", {}),
                )
                self._last_status = status
                return status
            except Exception as e:
                logger.warning(f"Browser check '{self.name}' failed: {e}")
                status = ServiceStatus(
                    name=self.name, available=False,
                    summary=f"{self.name}チェックエラー", last_check=time.time(),
                    error=str(e)[:200],
                )
                self._last_status = status
                return status


class ServiceCheckerManager:
    """Manages multiple service checkers with independent polling loops."""

    def __init__(self, mqtt_publisher):
        self._checkers: list[BaseChecker] = []
        self._mqtt = mqtt_publisher
        self._statuses: dict[str, ServiceStatus] = {}

    def register(self, checker: BaseChecker):
        self._checkers.append(checker)
        logger.info(f"Service checker registered: {checker.name} (interval={checker.interval}s)")

    async def run(self):
        """Start all checker loops as concurrent tasks."""
        if not self._checkers:
            logger.info("No service checkers registered")
            return
        logger.info(f"Starting {len(self._checkers)} service checker(s)")
        tasks = [asyncio.create_task(self._checker_loop(c)) for c in self._checkers]
        await asyncio.gather(*tasks)

    async def _checker_loop(self, checker: BaseChecker):
        while True:
            try:
                prev = self._statuses.get(checker.name)
                prev_count = prev.unread_count if prev else 0
                status = await checker.check()
                self._statuses[checker.name] = status

                # Publish status to MQTT
                payload = asdict(status)
                self._mqtt.publish(f"hems/services/{checker.name}/status", payload)

                # Edge trigger: unread count increased
                if status.unread_count > prev_count:
                    self._mqtt.publish(f"hems/services/{checker.name}/event", {
                        "type": "unread_increased",
                        "name": checker.name,
                        "prev_count": prev_count,
                        "new_count": status.unread_count,
                        "summary": status.summary,
                    })
                    logger.info(f"Service event: {checker.name} unread {prev_count} → {status.unread_count}")

            except Exception as e:
                logger.error(f"Checker loop error ({checker.name}): {e}")

            await asyncio.sleep(checker.interval)

    def get_status(self) -> dict:
        """Return all cached statuses for REST API."""
        return {
            name: asdict(status)
            for name, status in self._statuses.items()
        }
