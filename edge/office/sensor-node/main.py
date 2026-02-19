import machine
import dht
import time
import sys

# Add shared library path
sys.path.insert(0, "/lib")

from soms_mcp import MCPDevice

# Hardware Setup
sensor = dht.DHT22(machine.Pin(4))
led = machine.Pin(2, machine.Pin.OUT)

def set_indicator(state="on"):
    if state == "on":
        led.value(1)
    else:
        led.value(0)
    return {"status": "ok", "led": state}

def get_sensor_data():
    sensor.measure()
    return {
        "temperature": sensor.temperature(),
        "humidity": sensor.humidity(),
    }

def main():
    device = MCPDevice()

    # Register Tools
    device.register_tool("set_indicator", set_indicator)
    device.register_tool("get_status", get_sensor_data)

    try:
        device.connect()
    except Exception:
        print("Connection failed, resetting...")
        machine.reset()

    last_report = 0

    while True:
        try:
            device.loop()

            now = time.time()
            if now - last_report > device.report_interval:
                try:
                    data = get_sensor_data()
                    device.publish_sensor_data(data)
                except OSError:
                    print("Failed to read sensor")
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
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
