
import machine
import time

def scan_loop():
    print("Starting Periodic I2C Scan Loop...")
    print("Please connect BME680 to D4/D5 or try swapping wires.")
    
    # Priority pairs
    pairs = [
        (6, 7), (7, 6),
        (4, 5), (5, 4),
        (2, 3), (3, 2),
        (22, 23), (23, 22),
        (20, 21), (21, 20),
        (0, 1), (1, 0)
    ]
    
    while True:
        found_any = False
        for sda, scl in pairs:
            try:
                # Short timeout to keep loop responsive
                i2c = machine.I2C(0, sda=machine.Pin(sda), scl=machine.Pin(scl), freq=100000, timeout=1000)
                devs = i2c.scan()
                if devs:
                    print(f"\n!!!!!!!! FOUND DEVICES: {devs} at SDA={sda}, SCL={scl} !!!!!!!!\n")
                    found_any = True
                    # Beep or blink if possible, but print is safest
                else:
                    # print(f".", end="") # minimal output
                    pass
            except Exception as e:
                pass
        
        if not found_any:
            print(".", end="")
        
        time.sleep(1)

if __name__ == "__main__":
    scan_loop()
