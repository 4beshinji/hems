"""Thin wrapper around MicroPython's built-in dht module."""

from machine import Pin
import dht


class DHTSensor:
    """Unified DHT11/DHT22 interface matching the driver pattern."""

    def __init__(self, pin_num, sensor_type="dht22"):
        self._pin = Pin(pin_num)
        if sensor_type == "dht11":
            self._sensor = dht.DHT11(self._pin)
        else:
            self._sensor = dht.DHT22(self._pin)

    def read_sensor(self):
        self._sensor.measure()
        return {
            "temperature": self._sensor.temperature(),
            "humidity": self._sensor.humidity(),
        }
