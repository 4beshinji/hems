"""SHT30/SHT31 I2C temperature & humidity sensor driver for MicroPython."""

import time
try:
    import struct
except ImportError:
    import ustruct as struct

# Default I2C addresses (ADDR pin low = 0x44, ADDR pin high = 0x45)
KNOWN_ADDRESSES = (0x44, 0x45)

# Commands
_CMD_SINGLE_HIGH = b'\x24\x00'  # Single-shot, high repeatability


class SHT3x:
    def __init__(self, i2c, address=0x44):
        self._i2c = i2c
        self._address = address
        # Verify communication with a soft reset
        self._i2c.writeto(self._address, b'\x30\xA2')
        time.sleep_ms(2)

    def read_sensor(self):
        self._i2c.writeto(self._address, _CMD_SINGLE_HIGH)
        time.sleep_ms(16)  # Max measurement time for high repeatability
        data = self._i2c.readfrom(self._address, 6)

        # Validate CRC for temperature (bytes 0-1, CRC byte 2)
        if self._crc8(data[0:2]) != data[2]:
            raise RuntimeError("SHT3x temperature CRC error")
        # Validate CRC for humidity (bytes 3-4, CRC byte 5)
        if self._crc8(data[3:5]) != data[5]:
            raise RuntimeError("SHT3x humidity CRC error")

        raw_temp = (data[0] << 8) | data[1]
        raw_hum = (data[3] << 8) | data[4]

        temperature = -45.0 + 175.0 * raw_temp / 65535.0
        humidity = 100.0 * raw_hum / 65535.0

        return {
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
        }

    @staticmethod
    def _crc8(data):
        """CRC-8 with polynomial 0x31 (x^8 + x^5 + x^4 + 1), init 0xFF."""
        crc = 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x31
                else:
                    crc = crc << 1
                crc &= 0xFF
        return crc
