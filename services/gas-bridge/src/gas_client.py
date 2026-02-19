"""
HTTP client for GAS Web App — fetches data from Google Apps Script.
"""
import aiohttp
from loguru import logger


class GASClient:
    """Async HTTP client for GAS Web App endpoints."""

    def __init__(self, webapp_url: str, api_key: str):
        self.webapp_url = webapp_url.rstrip("/")
        self.api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def start(self):
        self._session = aiohttp.ClientSession()

    async def stop(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def fetch(self, action: str, **params) -> dict | None:
        """Fetch data from GAS Web App.

        Args:
            action: The action parameter (e.g. 'calendar_today', 'gmail_summary')
            **params: Additional query parameters (e.g. hours=24, count=10)

        Returns:
            Parsed JSON dict or None on error.
        """
        if not self._session:
            return None

        query = {"key": self.api_key, "action": action, **params}

        try:
            async with self._session.get(
                self.webapp_url, params=query, timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"GAS request failed: action={action} status={resp.status}")
                    return None
                data = await resp.json(content_type=None)
                if "error" in data:
                    logger.warning(f"GAS error: action={action} error={data['error']}")
                    return None
                return data
        except aiohttp.ClientError as e:
            logger.warning(f"GAS request error: action={action} {e}")
            return None
        except Exception as e:
            logger.error(f"GAS unexpected error: action={action} {e}")
            return None
