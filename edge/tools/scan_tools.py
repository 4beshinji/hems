
import machine
import time

LED_PIN = 15

def blink(n=3):
    try:
        led = machine.Pin(LED_PIN, machine.Pin.OUT)
        for _ in range(n):
            led.value(1)
            time.sleep(0.1)
            led.value(0)
            time.sleep(0.1)
    except:
        pass

def scan_i2c():
    print("Starting I2C Scan...")
    
    # Prioritize likely pins
    # XIAO ESP32C6: D4(SDA), D5(SCL)
    # Mapping variants: (4,5), (2,3), (6,7), (22,23), (21,20)
    pairs = [
        (4, 5), (5, 4),
        (2, 3), (3, 2),
        (6, 7), (7, 6),
        (22, 23), (23, 22),
        (21, 20), (20, 21),
        (0, 1), (1, 0)
    ]
    
    for sda, scl in pairs:
        print(f"Checking SDA={sda}, SCL={scl}...", end="")
        try:
            i2c = machine.I2C(0, sda=machine.Pin(sda), scl=machine.Pin(scl), freq=100000, timeout=1000)
            devs = i2c.scan()
            if devs:
                print(f" FOUND! Devices: {devs}")
                return (sda, scl, devs)
            else:
                print(" No devices.")
        except Exception as e:
            print(f" Error: {e}")
            
    print("Scan complete. No devices found in priority list.")
    return None

def main():
    print("Scan Tool Started.")
    blink()
    scan_i2c()
    print("Done.")

if __name__ == "__main__":
    main()
