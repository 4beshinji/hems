"""PIR motion sensor driver (HC-SR501 / AM312 / any digital output PIR)."""

from machine import Pin


class PIRSensor:
    def __init__(self, pin_num):
        self._pin = Pin(pin_num, Pin.IN)

    def read_sensor(self):
        return {"motion": int(self._pin.value())}
