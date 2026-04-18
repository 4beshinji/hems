"""
Weather API clients — JMA (気象庁) and OpenWeatherMap.
"""

import time

import aiohttp
from loguru import logger


class WeatherData:
    """Normalized weather data from any provider."""

    def __init__(
        self,
        *,
        provider: str = "",
        temperature: float = None,
        feels_like: float = None,
        humidity: int = None,
        pressure: float = None,
        wind_speed: float = None,
        wind_direction: str = "",
        weather_main: str = "",
        weather_description: str = "",
        icon: str = "",
        clouds: int = None,
        rain_1h: float = None,
        visibility: int = None,
        uv_index: float = None,
        timestamp: float = 0,
    ):
        self.provider = provider
        self.temperature = temperature
        self.feels_like = feels_like
        self.humidity = humidity
        self.pressure = pressure
        self.wind_speed = wind_speed
        self.wind_direction = wind_direction
        self.weather_main = weather_main
        self.weather_description = weather_description
        self.icon = icon
        self.clouds = clouds
        self.rain_1h = rain_1h
        self.visibility = visibility
        self.uv_index = uv_index
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> dict:
        d = {"provider": self.provider, "timestamp": self.timestamp}
        if self.temperature is not None:
            d["temperature"] = self.temperature
        if self.feels_like is not None:
            d["feels_like"] = self.feels_like
        if self.humidity is not None:
            d["humidity"] = self.humidity
        if self.pressure is not None:
            d["pressure"] = self.pressure
        if self.wind_speed is not None:
            d["wind_speed"] = self.wind_speed
        if self.wind_direction:
            d["wind_direction"] = self.wind_direction
        if self.weather_main:
            d["weather_main"] = self.weather_main
        if self.weather_description:
            d["weather_description"] = self.weather_description
        if self.icon:
            d["icon"] = self.icon
        if self.clouds is not None:
            d["clouds"] = self.clouds
        if self.rain_1h is not None:
            d["rain_1h"] = self.rain_1h
        if self.visibility is not None:
            d["visibility"] = self.visibility
        if self.uv_index is not None:
            d["uv_index"] = self.uv_index
        return d


class ForecastEntry:
    """Single forecast time slot."""

    def __init__(
        self,
        *,
        dt: str = "",
        temperature_max: float = None,
        temperature_min: float = None,
        weather_main: str = "",
        weather_description: str = "",
        pop: int = None,
        rain_mm: float = None,
        wind_speed: float = None,
    ):
        self.dt = dt
        self.temperature_max = temperature_max
        self.temperature_min = temperature_min
        self.weather_main = weather_main
        self.weather_description = weather_description
        self.pop = pop  # probability of precipitation (%)
        self.rain_mm = rain_mm
        self.wind_speed = wind_speed

    def to_dict(self) -> dict:
        d = {"dt": self.dt}
        if self.temperature_max is not None:
            d["temperature_max"] = self.temperature_max
        if self.temperature_min is not None:
            d["temperature_min"] = self.temperature_min
        if self.weather_main:
            d["weather_main"] = self.weather_main
        if self.weather_description:
            d["weather_description"] = self.weather_description
        if self.pop is not None:
            d["pop"] = self.pop
        if self.rain_mm is not None:
            d["rain_mm"] = self.rain_mm
        if self.wind_speed is not None:
            d["wind_speed"] = self.wind_speed
        return d


class WeatherAlert:
    """Weather warning/advisory."""

    def __init__(self, *, title: str = "", description: str = "", severity: str = "", start: str = "", end: str = ""):
        self.title = title
        self.description = description
        self.severity = severity  # warning | advisory | watch
        self.start = start
        self.end = end

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "start": self.start,
            "end": self.end,
        }


class JMAClient:
    """気象庁 JSON API client (no API key required)."""

    BASE_URL = "https://www.jma.go.jp/bosai"

    # JMA weather code → description mapping
    WEATHER_CODES = {
        "100": "晴れ",
        "101": "晴れ時々曇り",
        "102": "晴れ一時雨",
        "110": "晴れ後曇り",
        "111": "晴れ後曇り一時雨",
        "200": "曇り",
        "201": "曇り時々晴れ",
        "202": "曇り一時雨",
        "210": "曇り後晴れ",
        "211": "曇り後雨",
        "300": "雨",
        "301": "雨時々曇り",
        "302": "雨一時雪",
        "303": "雨時々雪",
        "311": "雨後曇り",
        "313": "雨後晴れ",
        "400": "雪",
        "401": "雪時々曇り",
        "402": "雪一時雨",
    }

    # JMA weather code → simplified main category
    WEATHER_MAIN = {
        "100": "Clear",
        "101": "Clouds",
        "102": "Rain",
        "110": "Clouds",
        "111": "Rain",
        "200": "Clouds",
        "201": "Clouds",
        "202": "Rain",
        "210": "Clouds",
        "211": "Rain",
        "300": "Rain",
        "301": "Rain",
        "302": "Snow",
        "303": "Snow",
        "311": "Rain",
        "313": "Rain",
        "400": "Snow",
        "401": "Snow",
        "402": "Snow",
    }

    def __init__(self, area_code: str, detail_code: str):
        self.area_code = area_code
        self.detail_code = detail_code
        self._session: aiohttp.ClientSession | None = None

    async def start(self):
        self._session = aiohttp.ClientSession()

    async def stop(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def _get_json(self, url: str) -> dict | list | None:
        if not self._session:
            return None
        try:
            async with self._session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"JMA request failed: {url} status={resp.status}")
                    return None
                return await resp.json(content_type=None)
        except Exception as e:
            logger.warning(f"JMA request error: {url} {e}")
            return None

    async def get_current(self) -> WeatherData | None:
        """Get current weather from JMA overview forecast."""
        url = f"{self.BASE_URL}/forecast/data/overview_forecast/{self.area_code}.json"
        data = await self._get_json(url)
        if not data:
            return None

        desc = data.get("text", "")

        # Get detailed forecast for temperature/weather code
        forecast_data = await self._get_forecast_raw()
        if not forecast_data:
            return WeatherData(
                provider="jma",
                weather_description=desc[:200],
            )

        # Extract current weather from latest time series
        current = self._parse_current_from_forecast(forecast_data)
        current.weather_description = desc[:200] if not current.weather_description else current.weather_description
        return current

    async def _get_forecast_raw(self) -> list | None:
        url = f"{self.BASE_URL}/forecast/data/forecast/{self.area_code}.json"
        return await self._get_json(url)

    def _parse_current_from_forecast(self, data: list) -> WeatherData:
        """Extract current conditions from JMA forecast data."""
        result = WeatherData(provider="jma")

        if not data:
            return result

        # First element contains weather/wind/wave forecasts
        ts_list = data[0].get("timeSeries", [])
        if not ts_list:
            return result

        # Find our detail_code area in the forecast
        for ts in ts_list:
            areas = ts.get("areas", [])
            for area in areas:
                area_code = area.get("area", {}).get("code", "")
                if area_code != self.detail_code:
                    continue

                # Weather codes
                weather_codes = area.get("weatherCodes", [])
                if weather_codes:
                    code = weather_codes[0]
                    result.weather_main = self.WEATHER_MAIN.get(code, "")
                    result.weather_description = self.WEATHER_CODES.get(code, "")
                    result.icon = code

                # Wind
                winds = area.get("winds", [])
                if winds:
                    result.wind_direction = winds[0]

                # Precipitation probability
                pops = area.get("pops", [])
                if pops and pops[0] not in ("", None):
                    try:
                        result.rain_1h = float(pops[0])
                    except (ValueError, TypeError):
                        pass

        # Second element often has temperature data
        if len(data) > 1:
            ts_list2 = data[1].get("timeSeries", [])
            for ts in ts_list2:
                areas = ts.get("areas", [])
                for area in areas:
                    area_code = area.get("area", {}).get("code", "")
                    if area_code != self.detail_code:
                        continue
                    temps_max = area.get("tempsMax", [])
                    temps_min = area.get("tempsMin", [])
                    if temps_max and temps_max[0] not in ("", None):
                        try:
                            result.temperature = float(temps_max[0])
                        except (ValueError, TypeError):
                            pass
                    elif temps_min and temps_min[0] not in ("", None):
                        try:
                            result.temperature = float(temps_min[0])
                        except (ValueError, TypeError):
                            pass

        return result

    async def get_forecast(self) -> list[ForecastEntry]:
        """Get multi-day forecast from JMA."""
        data = await self._get_forecast_raw()
        if not data:
            return []

        entries = []

        # Parse weekly forecast (data[1] if available)
        if len(data) > 1:
            ts_list = data[1].get("timeSeries", [])
            for ts in ts_list:
                time_defines = ts.get("timeDefines", [])
                areas = ts.get("areas", [])
                for area in areas:
                    area_code = area.get("area", {}).get("code", "")
                    if area_code != self.detail_code:
                        continue

                    weather_codes = area.get("weatherCodes", [])
                    pops = area.get("pops", [])
                    temps_max = area.get("tempsMax", [])
                    temps_min = area.get("tempsMin", [])

                    for i, dt in enumerate(time_defines):
                        entry = ForecastEntry(dt=dt)
                        if i < len(weather_codes):
                            code = weather_codes[i]
                            entry.weather_main = self.WEATHER_MAIN.get(code, "")
                            entry.weather_description = self.WEATHER_CODES.get(code, "")
                        if i < len(pops) and pops[i] not in ("", None):
                            try:
                                entry.pop = int(pops[i])
                            except (ValueError, TypeError):
                                pass
                        if i < len(temps_max) and temps_max[i] not in ("", None):
                            try:
                                entry.temperature_max = float(temps_max[i])
                            except (ValueError, TypeError):
                                pass
                        if i < len(temps_min) and temps_min[i] not in ("", None):
                            try:
                                entry.temperature_min = float(temps_min[i])
                            except (ValueError, TypeError):
                                pass
                        entries.append(entry)

        # Also parse short-term precipitation probability from data[0]
        if data:
            ts_list = data[0].get("timeSeries", [])
            for ts in ts_list:
                time_defines = ts.get("timeDefines", [])
                areas = ts.get("areas", [])
                for area in areas:
                    area_code = area.get("area", {}).get("code", "")
                    if area_code != self.detail_code:
                        continue
                    pops = area.get("pops", [])
                    if pops:
                        for i, dt in enumerate(time_defines):
                            if i < len(pops) and pops[i] not in ("", None):
                                # Check if entry already exists for this time
                                existing = next((e for e in entries if e.dt == dt), None)
                                if existing:
                                    try:
                                        existing.pop = int(pops[i])
                                    except (ValueError, TypeError):
                                        pass
                                else:
                                    try:
                                        entries.append(
                                            ForecastEntry(
                                                dt=dt,
                                                pop=int(pops[i]),
                                            )
                                        )
                                    except (ValueError, TypeError):
                                        pass

        return entries

    async def get_alerts(self) -> list[WeatherAlert]:
        """Get weather warnings/advisories from JMA."""
        url = f"{self.BASE_URL}/warning/data/warning/{self.area_code}.json"
        data = await self._get_json(url)
        if not data:
            return []

        alerts = []
        for area_warning in data.get("areaTypes", []):
            for area in area_warning.get("areas", []):
                for warning in area.get("warnings", []):
                    status = warning.get("status", "")
                    if status in ("発表", "継続"):
                        code = warning.get("code", "")
                        alerts.append(
                            WeatherAlert(
                                title=self._warning_code_to_name(code),
                                description=f"{area.get('name', '')} {status}",
                                severity="warning" if int(code) < 10 else "advisory",
                            )
                        )
        return alerts

    @staticmethod
    def _warning_code_to_name(code: str) -> str:
        names = {
            "02": "暴風雪警報",
            "03": "大雨警報",
            "04": "洪水警報",
            "05": "暴風警報",
            "06": "大雪警報",
            "07": "波浪警報",
            "08": "高潮警報",
            "10": "大雨注意報",
            "12": "大雪注意報",
            "13": "風雪注意報",
            "14": "雷注意報",
            "15": "強風注意報",
            "16": "波浪注意報",
            "17": "融雪注意報",
            "18": "洪水注意報",
            "19": "高潮注意報",
            "20": "濃霧注意報",
            "21": "乾燥注意報",
            "22": "なだれ注意報",
            "23": "低温注意報",
            "24": "霜注意報",
            "25": "着氷注意報",
            "26": "着雪注意報",
        }
        return names.get(code, f"気象警報(code={code})")


class OWMClient:
    """OpenWeatherMap API client."""

    BASE_URL = "https://api.openweathermap.org/data/3.0"

    def __init__(self, api_key: str, lat: str, lon: str, units: str = "metric", lang: str = "ja"):
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.units = units
        self.lang = lang
        self._session: aiohttp.ClientSession | None = None

    async def start(self):
        self._session = aiohttp.ClientSession()

    async def stop(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def _get_json(self, url: str, params: dict) -> dict | None:
        if not self._session:
            return None
        try:
            async with self._session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"OWM request failed: status={resp.status}")
                    return None
                return await resp.json()
        except Exception as e:
            logger.warning(f"OWM request error: {e}")
            return None

    async def get_current(self) -> WeatherData | None:
        """Get current weather from OWM One Call API."""
        data = await self._get_json(
            f"{self.BASE_URL}/onecall",
            {
                "lat": self.lat,
                "lon": self.lon,
                "appid": self.api_key,
                "units": self.units,
                "lang": self.lang,
                "exclude": "minutely,hourly,daily,alerts",
            },
        )
        if not data or "current" not in data:
            return None

        c = data["current"]
        weather = c.get("weather", [{}])[0] if c.get("weather") else {}
        return WeatherData(
            provider="openweathermap",
            temperature=c.get("temp"),
            feels_like=c.get("feels_like"),
            humidity=c.get("humidity"),
            pressure=c.get("pressure"),
            wind_speed=c.get("wind_speed"),
            weather_main=weather.get("main", ""),
            weather_description=weather.get("description", ""),
            icon=weather.get("icon", ""),
            clouds=c.get("clouds"),
            rain_1h=c.get("rain", {}).get("1h"),
            visibility=c.get("visibility"),
            uv_index=c.get("uvi"),
        )

    async def get_forecast(self) -> list[ForecastEntry]:
        """Get daily forecast from OWM One Call API."""
        data = await self._get_json(
            f"{self.BASE_URL}/onecall",
            {
                "lat": self.lat,
                "lon": self.lon,
                "appid": self.api_key,
                "units": self.units,
                "lang": self.lang,
                "exclude": "current,minutely,hourly,alerts",
            },
        )
        if not data or "daily" not in data:
            return []

        entries = []
        for day in data["daily"]:
            weather = day.get("weather", [{}])[0] if day.get("weather") else {}
            entries.append(
                ForecastEntry(
                    dt=str(day.get("dt", "")),
                    temperature_max=day.get("temp", {}).get("max"),
                    temperature_min=day.get("temp", {}).get("min"),
                    weather_main=weather.get("main", ""),
                    weather_description=weather.get("description", ""),
                    pop=int(day.get("pop", 0) * 100) if day.get("pop") is not None else None,
                    rain_mm=day.get("rain"),
                    wind_speed=day.get("wind_speed"),
                )
            )
        return entries

    async def get_alerts(self) -> list[WeatherAlert]:
        """Get weather alerts from OWM One Call API."""
        data = await self._get_json(
            f"{self.BASE_URL}/onecall",
            {
                "lat": self.lat,
                "lon": self.lon,
                "appid": self.api_key,
                "units": self.units,
                "lang": self.lang,
                "exclude": "current,minutely,hourly,daily",
            },
        )
        if not data or "alerts" not in data:
            return []

        return [
            WeatherAlert(
                title=a.get("event", ""),
                description=a.get("description", "")[:200],
                severity="warning",
                start=str(a.get("start", "")),
                end=str(a.get("end", "")),
            )
            for a in data["alerts"]
        ]
