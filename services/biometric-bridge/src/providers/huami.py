"""
Huami cloud API provider — polls biometric data from Xiaomi/Huami cloud.
Supports Xiaomi Smart Band 8/9/10 and Amazfit devices via Mi Fitness app data.

Auth: run `pip install huami-token && huami-token --method xiaomi` to obtain
HUAMI_AUTH_TOKEN and HUAMI_USER_ID, then set them in .env.
"""
import json
import time
from datetime import datetime, timezone

import aiohttp
from loguru import logger

from data_processor import BiometricReading
from providers.base import BiometricProvider


class HuamiProvider(BiometricProvider):
    """Polls Huami (Mi Fitness) cloud API for biometric data (batch summary)."""

    SERVERS = {
        "us": "api-mifit-us2.huami.com",
        "cn": "api-mifit.huami.com",
        "eu": "api-mifit-de.huami.com",
        "sg": "api-mifit-sg.huami.com",
        "ru": "api-mifit-ru.huami.com",
    }

    def __init__(
        self,
        auth_token: str = "",
        user_id: str = "",
        server_region: str = "us",
        poll_interval: int = 900,
    ):
        self._auth_token = auth_token
        self._user_id = user_id
        self._server = self.SERVERS.get(server_region, self.SERVERS["us"])
        self._poll_interval = poll_interval
        self._session: aiohttp.ClientSession | None = None
        self._latest: BiometricReading | None = None
        self._running = False
        self._last_hr_ts: float = 0  # track last HR timestamp to avoid re-processing

    @property
    def name(self) -> str:
        return "huami"

    async def start(self):
        if not self._auth_token or not self._user_id:
            logger.info(
                "Huami provider disabled (no HUAMI_AUTH_TOKEN / HUAMI_USER_ID). "
                "Run: pip install huami-token && huami-token --method xiaomi"
            )
            return
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        self._running = True
        logger.info(f"Huami provider started (server={self._server}, poll={self._poll_interval}s)")

    async def stop(self):
        self._running = False
        if self._session:
            await self._session.close()
            self._session = None

    async def get_latest(self) -> BiometricReading | None:
        return self._latest

    async def poll(self) -> BiometricReading | None:
        """Poll Huami API for today's band data summary. Returns None on failure."""
        if not self._running or not self._session:
            return None

        today = datetime.now().strftime("%Y-%m-%d")
        try:
            data = await self._fetch_band_data(today, today)
        except Exception as e:
            logger.error(f"Huami API fetch failed: {e}")
            return None

        if not data:
            return None

        reading = self._parse_band_data(data)
        if reading:
            self._latest = reading
        return reading

    async def _fetch_band_data(self, from_date: str, to_date: str) -> list[dict] | None:
        """Fetch band_data.json from Huami API."""
        url = f"https://{self._server}/v1/data/band_data.json"
        params = {
            "query_type": "summary",
            "device_type": "0",
            "userid": self._user_id,
            "from_date": from_date,
            "to_date": to_date,
        }
        headers = {"apptoken": self._auth_token}

        async with self._session.get(url, params=params, headers=headers) as resp:
            if resp.status == 401:
                logger.error(
                    "Huami API auth failed (401). Token may have expired. "
                    "Re-run: huami-token --method xiaomi"
                )
                return None
            if resp.status != 200:
                logger.error(f"Huami API HTTP {resp.status}: {await resp.text()}")
                return None

            body = await resp.json()

        if body.get("code") != 0:
            logger.error(f"Huami API error: {body.get('message', 'unknown')}")
            return None

        return body.get("data", [])

    def _parse_band_data(self, entries: list[dict]) -> BiometricReading | None:
        """Parse band_data.json response into BiometricReading."""
        if not entries:
            return None

        # Use the latest day's entry
        entry = entries[-1]
        reading = BiometricReading(
            timestamp=time.time(),
            provider=self.name,
        )

        # Parse summary (steps, sleep, calories)
        summary_raw = entry.get("summary", "")
        if summary_raw:
            try:
                summary = json.loads(summary_raw) if isinstance(summary_raw, str) else summary_raw
                self._parse_summary(summary, reading)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Huami summary parse error: {e}")

        # Parse HR data
        hr_raw = entry.get("data_hr", "")
        if hr_raw:
            try:
                hr_data = json.loads(hr_raw) if isinstance(hr_raw, str) else hr_raw
                self._parse_hr(hr_data, reading)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Huami HR parse error: {e}")

        # Parse SpO2 data (newer devices)
        spo2_raw = entry.get("data_spo2", "")
        if spo2_raw:
            try:
                spo2_data = json.loads(spo2_raw) if isinstance(spo2_raw, str) else spo2_raw
                self._parse_spo2(spo2_data, reading)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Huami SpO2 parse error: {e}")

        # Parse stress data (newer devices)
        stress_raw = entry.get("data_stress", "")
        if stress_raw:
            try:
                stress_data = json.loads(stress_raw) if isinstance(stress_raw, str) else stress_raw
                self._parse_stress(stress_data, reading)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Huami stress parse error: {e}")

        return reading

    def _parse_summary(self, summary: dict, reading: BiometricReading):
        """Parse summary block (steps, sleep, goal)."""
        # Steps
        stp = summary.get("stp", {})
        if isinstance(stp, dict):
            if "ttl" in stp:
                reading.steps = int(stp["ttl"])
            if "cal" in stp:
                reading.calories = int(stp["cal"])

        # Goal
        goal = summary.get("goal")
        if goal is not None:
            reading.steps_goal = int(goal)

        # Sleep
        slp = summary.get("slp", {})
        if isinstance(slp, dict):
            lt = slp.get("lt")  # light sleep minutes
            dp = slp.get("dp")  # deep sleep minutes
            rms = slp.get("rms", 0)  # REM sleep minutes (newer devices)
            st = slp.get("st")  # sleep start
            ed = slp.get("ed")  # sleep end

            if lt is not None:
                reading.sleep_light_minutes = int(lt)
            if dp is not None:
                reading.sleep_deep_minutes = int(dp)
            if rms:
                reading.sleep_rem_minutes = int(rms)

            total = (reading.sleep_light_minutes or 0) + \
                    (reading.sleep_deep_minutes or 0) + \
                    (reading.sleep_rem_minutes or 0)
            if total > 0:
                reading.sleep_duration_minutes = total

            if st is not None:
                reading.sleep_start_ts = self._parse_timestamp(st)
            if ed is not None:
                reading.sleep_end_ts = self._parse_timestamp(ed)

    def _parse_hr(self, hr_data: dict, reading: BiometricReading):
        """Parse heart rate data — use latest reading."""
        rate_list = hr_data.get("rate_list", [])
        if not rate_list:
            return

        # rate_list entries: {"time": minutes_from_midnight, "hr": value}
        # or {"start_time": unix_ts, "rate": value}
        latest = rate_list[-1]
        hr = latest.get("hr") or latest.get("rate")
        if hr is not None and int(hr) > 0:
            reading.heart_rate = int(hr)

        # Compute resting HR (minimum of last readings, excluding 0)
        valid_hrs = [
            int(r.get("hr") or r.get("rate", 0))
            for r in rate_list
            if int(r.get("hr") or r.get("rate", 0)) > 30
        ]
        if valid_hrs:
            reading.resting_heart_rate = min(valid_hrs)

    def _parse_spo2(self, spo2_data: dict, reading: BiometricReading):
        """Parse SpO2 data — use latest reading."""
        spo2_list = spo2_data.get("spo2_list", []) or spo2_data.get("list", [])
        if not spo2_list:
            # Single value format
            val = spo2_data.get("spo2") or spo2_data.get("value")
            if val is not None:
                reading.spo2 = int(val)
            return

        latest = spo2_list[-1]
        val = latest.get("spo2") or latest.get("value")
        if val is not None and int(val) > 0:
            reading.spo2 = int(val)

    def _parse_stress(self, stress_data: dict, reading: BiometricReading):
        """Parse stress data — use latest reading."""
        stress_list = stress_data.get("stress_list", []) or stress_data.get("list", [])
        if not stress_list:
            val = stress_data.get("stress") or stress_data.get("value")
            if val is not None:
                reading.stress_level = int(val)
            return

        latest = stress_list[-1]
        val = latest.get("stress") or latest.get("value")
        if val is not None and int(val) > 0:
            reading.stress_level = int(val)

    @staticmethod
    def _parse_timestamp(ts) -> float:
        """Convert Huami timestamp (unix int, unix float, or datetime string) to float."""
        if isinstance(ts, (int, float)):
            # Could be seconds or milliseconds
            if ts > 1e12:
                return float(ts) / 1000.0
            return float(ts)
        if isinstance(ts, str):
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                return dt.replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                pass
            try:
                return float(ts)
            except ValueError:
                pass
        return 0.0
