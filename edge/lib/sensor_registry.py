"""
SensorRegistry — config-driven sensor initialization and reading.

Manages I2C bus lazy-init, I2C address auto-detection, UART probe,
and per-sensor error isolation.

Usage:
    from board_pins import get_board_pins
    from sensor_registry import SensorRegistry

    pins = get_board_pins("xiao_esp32_c6")
    registry = SensorRegistry(pins)
    registry.add_sensor({"type": "bme680", "bus": "i2c", "address": "auto"})
    registry.add_sensor({"type": "dht22", "bus": "gpio"})
    data = registry.read_all()  # {"temperature": 22.1, "humidity": 45, ...}
"""

from machine import Pin, SoftI2C


# Known I2C addresses per sensor type
_I2C_ADDRESS_MAP = {
    "bme680": (0x77, 0x76),
    "bh1750": (0x23, 0x5C),
    "sht31":  (0x44, 0x45),
    "sht30":  (0x44, 0x45),
}


class SensorRegistry:
    def __init__(self, board_pins):
        self._pins = board_pins
        self._sensors = []       # list of (name, driver_instance)
        self._i2c = None         # lazy-init
        self._i2c_scanned = None # cached scan results

    # ---- I2C lazy init ----

    def _ensure_i2c(self):
        if self._i2c is None:
            sda = self._pins["i2c_sda"]
            scl = self._pins["i2c_scl"]
            self._i2c = SoftI2C(sda=Pin(sda), scl=Pin(scl))
            self._i2c_scanned = self._i2c.scan()
            if self._i2c_scanned:
                print("I2C devices found:", [hex(a) for a in self._i2c_scanned])
            else:
                print("I2C: no devices found")
        return self._i2c

    def _resolve_i2c_address(self, sensor_type, cfg_address):
        """Resolve I2C address: explicit int, or 'auto' to scan known addresses."""
        if isinstance(cfg_address, int):
            return cfg_address
        if cfg_address == "auto" and sensor_type in _I2C_ADDRESS_MAP:
            self._ensure_i2c()
            for candidate in _I2C_ADDRESS_MAP[sensor_type]:
                if candidate in self._i2c_scanned:
                    return candidate
            raise RuntimeError(
                f"{sensor_type}: no device at known addresses "
                f"{[hex(a) for a in _I2C_ADDRESS_MAP[sensor_type]]}"
            )
        raise ValueError(f"{sensor_type}: invalid address '{cfg_address}'")

    # ---- Sensor factories ----

    def _init_bme680(self, cfg):
        from drivers.bme680_driver import BME680_I2C
        i2c = self._ensure_i2c()
        addr = self._resolve_i2c_address("bme680", cfg.get("address", "auto"))
        return BME680_I2C(i2c, address=addr)

    def _init_sht3x(self, cfg):
        from drivers.sht3x_driver import SHT3x
        sensor_type = cfg["type"]  # "sht31" or "sht30"
        i2c = self._ensure_i2c()
        addr = self._resolve_i2c_address(sensor_type, cfg.get("address", "auto"))
        return SHT3x(i2c, address=addr)

    def _init_bh1750(self, cfg):
        from drivers.bh1750_driver import BH1750
        i2c = self._ensure_i2c()
        addr = self._resolve_i2c_address("bh1750", cfg.get("address", "auto"))
        return BH1750(i2c, address=addr)

    def _init_mhz19c(self, cfg):
        from drivers.mhz19_driver import MHZ19C
        uart_id = cfg.get("uart_id", 1)
        tx = cfg.get("tx_pin", self._pins["uart1_tx"])
        rx = cfg.get("rx_pin", self._pins["uart1_rx"])
        sensor = MHZ19C(uart_id, rx_pin=rx, tx_pin=tx)
        # Probe: attempt one read to verify sensor responds
        co2 = sensor.read_co2()
        if co2 is None:
            raise RuntimeError("MH-Z19C: no response on probe read")
        print(f"MH-Z19C probe OK: {co2} ppm")
        return sensor

    def _init_dht(self, cfg):
        from drivers.dht_wrapper import DHTSensor
        pin = cfg.get("pin", self._pins["dht_pin"])
        sensor_type = cfg["type"]  # "dht22" or "dht11"
        return DHTSensor(pin, sensor_type=sensor_type)

    def _init_pir(self, cfg):
        from drivers.pir_driver import PIRSensor
        pin = cfg.get("pin", self._pins["pir_pin"])
        return PIRSensor(pin)

    # ---- Public API ----

    _FACTORIES = {
        "bme680":  "_init_bme680",
        "sht31":   "_init_sht3x",
        "sht30":   "_init_sht3x",
        "bh1750":  "_init_bh1750",
        "mhz19c":  "_init_mhz19c",
        "dht22":   "_init_dht",
        "dht11":   "_init_dht",
        "pir":     "_init_pir",
    }

    def add_sensor(self, sensor_cfg):
        """
        Initialize a sensor from a config dict.

        sensor_cfg example:
            {"type": "bme680", "bus": "i2c", "address": "auto"}
            {"type": "dht22", "bus": "gpio", "pin": 4}
            {"type": "mhz19c", "bus": "uart", "uart_id": 1}

        Raises on failure — caller should catch and skip.
        """
        sensor_type = sensor_cfg["type"]
        factory_name = self._FACTORIES.get(sensor_type)
        if factory_name is None:
            raise ValueError(f"Unknown sensor type: {sensor_type}")
        factory = getattr(self, factory_name)
        driver = factory(sensor_cfg)
        self._sensors.append((sensor_type, driver))
        print(f"Sensor registered: {sensor_type}")

    def read_all(self):
        """
        Read all active sensors, returning a merged dict.
        Failed reads are skipped with a warning.
        """
        result = {}
        for name, driver in self._sensors:
            try:
                if name == "mhz19c":
                    co2 = driver.read_co2()
                    if co2 is not None:
                        result["co2"] = co2
                else:
                    data = driver.read_sensor()
                    result.update(data)
            except Exception as e:
                print(f"Read error ({name}): {e}")
        return result

    @property
    def sensor_count(self):
        return len(self._sensors)

    @property
    def sensor_names(self):
        return [name for name, _ in self._sensors]
