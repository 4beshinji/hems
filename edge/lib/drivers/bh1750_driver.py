"""BH1750 I2C ambient light sensor driver for MicroPython."""

import time


# Default I2C address (ADDR pin low = 0x23, ADDR pin high = 0x5C)
_BH1750_ADDR_LOW = 0x23
_BH1750_ADDR_HIGH = 0x5C
KNOWN_ADDRESSES = (0x23, 0x5C)

# Commands
_POWER_ON = 0x01
_CONTINUOUS_HIGH_RES = 0x10


class BH1750:
    def __init__(self, i2c, address=0x23):
        self._i2c = i2c
        self._address = address
        self._i2c.writeto(self._address, bytes([_POWER_ON]))

    def _read_lux(self):
        self._i2c.writeto(self._address, bytes([_CONTINUOUS_HIGH_RES]))
        time.sleep_ms(180)
        raw = self._i2c.readfrom(self._address, 2)
        return (raw[0] << 8 | raw[1]) / 1.2

    def read_sensor(self):
        return {"illuminance": round(self._read_lux(), 1)}
