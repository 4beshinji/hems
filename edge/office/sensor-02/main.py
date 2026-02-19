
import machine
import time
import sys

# Add shared library path
sys.path.insert(0, "/lib")

from soms_mcp import MCPDevice
from bme680_driver import BME680_I2C
from mhz19_driver import MHZ19C

# Pin Definitions (Seeed XIAO ESP32C6)
# BME680 (I2C): SDA=D5(GPIO23), SCL=D4(GPIO22)
# MH-Z19C (UART): TX=D1(GPIO1), RX=D0(GPIO0)
I2C_SDA_PIN = 23 # D5
I2C_SCL_PIN = 22 # D4
UART_TX_PIN = 1  # D1 (Connect to Sensor RX)
UART_RX_PIN = 0  # D0 (Connect to Sensor TX)

# --- Hardware Initialization ---
# I2C for BME680
i2c = None
bme = None
try:
    print(f"Initializing SoftI2C on SDA={I2C_SDA_PIN}, SCL={I2C_SCL_PIN}...")
    i2c = machine.SoftI2C(sda=machine.Pin(I2C_SDA_PIN, machine.Pin.PULL_UP),
                          scl=machine.Pin(I2C_SCL_PIN, machine.Pin.PULL_UP),
                          freq=100000, timeout=100000)
    devices = i2c.scan()
    print(f"I2C Scan Devices Found: {[hex(d) for d in devices]}")

    # Auto-detect address
    addr = None
    if 0x77 in devices:
        addr = 0x77
    elif 0x76 in devices:
        addr = 0x76

    if addr:
        bme = BME680_I2C(i2c, address=addr)
        print(f"BME680 initialized at {hex(addr)}.")
    else:
        print("BME680 NOT FOUND (tried 0x76, 0x77).")
except Exception as e:
    print(f"I2C/BME680 Init Error: {e}")

# MH-Z19C UART
mhz = None
try:
    print(f"Initializing MH-Z19C UART on TX={UART_TX_PIN}, RX={UART_RX_PIN}...")
    mhz = MHZ19C(1, rx_pin=UART_RX_PIN, tx_pin=UART_TX_PIN)
    print("MH-Z19C UART initialized.")
except Exception as e:
    print(f"UART/MH-Z19C Init Error: {e}")

def get_sensor_data():
    data = {}

    # BME680
    if bme:
        try:
            data.update(bme.read_sensor())
        except Exception as e:
            print(f"BME read error: {e}")

    # MH-Z19C
    if mhz:
        try:
            co2 = mhz.read_co2()
            if co2 is not None:
                data['co2'] = co2
        except Exception as e:
            print(f"MHZ read error: {e}")

    return data

def restart_device():
    """Restarts the ESP32."""
    machine.reset()
    return {"status": "restarting"}

# --- Device Setup (reads config.json for WiFi/MQTT/zone) ---
device = MCPDevice()

# Register Tools
device.register_tool("get_status", get_sensor_data)
device.register_tool("restart", restart_device)

def main():
    print(f"Starting Sensor Node {device.device_id}...")

    try:
        device.connect()
    except Exception as e:
        print(f"Failed to connect: {e}")
        time.sleep(10)
        machine.reset()

    last_report = 0

    while True:
        try:
            device.loop()

            # Periodic Telemetry
            now = time.time()
            if now - last_report > device.report_interval:
                sensor_data = get_sensor_data()
                print(f"Telemetry: {sensor_data}")

                if sensor_data:
                    device.publish_sensor_data(sensor_data)

                last_report = now

            time.sleep(0.1)

        except OSError as e:
            print(f"Connection error: {e}")
            time.sleep(5)
            try:
                device.reconnect()
            except Exception:
                print("Reconnect failed, resetting...")
                time.sleep(10)
                machine.reset()
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
