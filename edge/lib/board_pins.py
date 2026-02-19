"""
Board pin mappings for common ESP32 development boards.

Usage:
    from board_pins import get_board_pins
    pins = get_board_pins("xiao_esp32_c6")
    i2c = SoftI2C(sda=Pin(pins["i2c_sda"]), scl=Pin(pins["i2c_scl"]))
"""

BOARDS = {
    "esp32_devkitc": {
        "i2c_sda": 21,
        "i2c_scl": 22,
        "uart1_tx": 17,
        "uart1_rx": 16,
        "dht_pin": 4,
        "pir_pin": 13,
        "led": 2,
        "adc_battery": -1,
    },
    "xiao_esp32_c6": {
        "i2c_sda": 23,
        "i2c_scl": 22,
        "uart1_tx": 1,
        "uart1_rx": 0,
        "dht_pin": 2,
        "pir_pin": 3,
        "led": 15,
        "adc_battery": -1,
    },
    "xiao_esp32_s3": {
        "i2c_sda": 5,
        "i2c_scl": 6,
        "uart1_tx": 43,
        "uart1_rx": 44,
        "dht_pin": 1,
        "pir_pin": 2,
        "led": 21,
        "adc_battery": -1,
    },
    "xiao_esp32_c3": {
        "i2c_sda": 6,
        "i2c_scl": 7,
        "uart1_tx": 21,
        "uart1_rx": 20,
        "dht_pin": 4,
        "pir_pin": 5,
        "led": -1,
        "adc_battery": -1,
    },
    "esp32_cam": {
        "i2c_sda": 14,
        "i2c_scl": 15,
        "uart1_tx": 1,
        "uart1_rx": 3,
        "dht_pin": 13,
        "pir_pin": 12,
        "led": 33,
        "adc_battery": -1,
    },
}


def get_board_pins(board_name):
    """Return pin mapping dict for the given board, defaulting to esp32_devkitc."""
    return BOARDS.get(board_name, BOARDS["esp32_devkitc"])
