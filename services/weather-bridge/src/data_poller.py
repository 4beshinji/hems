"""
Data poller — fetches weather data on configured intervals and publishes to MQTT.
"""

import asyncio
import time

from loguru import logger

import config
from hems_common import MqttPublisher, publish_bridge_status


class DataPoller:
    """Manages periodic polling of weather data and MQTT publishing."""

    def __init__(self, client, mqtt_pub: MqttPublisher):
        self.client = client
        self.mqtt = mqtt_pub

        # Cached data for REST API
        self.current_data: dict | None = None
        self.forecast_data: list[dict] | None = None
        self.alerts_data: list[dict] | None = None

        self._last_update: dict[str, float] = {}
        self._connected = False

    async def poll_current(self):
        """Poll current weather data."""
        while True:
            try:
                current = await self.client.get_current()
                if current:
                    self.current_data = current.to_dict()
                    self._last_update["current"] = time.time()
                    self.mqtt.publish("hems/weather/current", self.current_data)
                    logger.debug(f"Published current weather: {current.weather_main}")

                self._update_bridge_status()
            except Exception as e:
                logger.error(f"Current weather poll error: {e}")

            await asyncio.sleep(config.CURRENT_INTERVAL)

    async def poll_forecast(self):
        """Poll forecast and alerts data."""
        while True:
            try:
                # Forecast
                forecast = await self.client.get_forecast()
                if forecast:
                    self.forecast_data = [f.to_dict() for f in forecast]
                    self._last_update["forecast"] = time.time()
                    self.mqtt.publish(
                        "hems/weather/forecast",
                        {
                            "entries": self.forecast_data,
                            "timestamp": time.time(),
                        },
                    )
                    logger.debug(f"Published forecast: {len(forecast)} entries")

                # Alerts
                alerts = await self.client.get_alerts()
                self.alerts_data = [a.to_dict() for a in alerts]
                self._last_update["alerts"] = time.time()
                if alerts:
                    self.mqtt.publish(
                        "hems/weather/alerts",
                        {
                            "alerts": self.alerts_data,
                            "timestamp": time.time(),
                        },
                    )
                    logger.info(f"Published {len(alerts)} weather alert(s)")

                self._update_bridge_status()
            except Exception as e:
                logger.error(f"Forecast poll error: {e}")

            await asyncio.sleep(config.FORECAST_INTERVAL)

    def _update_bridge_status(self):
        """Publish bridge connection status."""
        self._connected = True
        publish_bridge_status(
            self.mqtt,
            "weather",
            provider=config.WEATHER_PROVIDER,
            last_updates=self._last_update,
            timestamp=time.time(),
        )

    def get_status(self) -> dict:
        """Get current status for REST API."""
        return {
            "connected": self._connected,
            "provider": config.WEATHER_PROVIDER,
            "last_updates": self._last_update,
            "has_current": self.current_data is not None,
            "forecast_entries": len(self.forecast_data) if self.forecast_data else 0,
            "active_alerts": len(self.alerts_data) if self.alerts_data else 0,
        }
