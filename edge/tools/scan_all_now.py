
import machine
import time

def scan_all():
    print("--- COMPREHENSIVE SCAN ---")
    pairs = [
        (2, 3), (3, 2),       # Proposed
        (4, 5), (5, 4),       # Original / Strapping?
        (6, 7), (7, 6),       # Pin labels D6/D7?
        (22, 23), (23, 22),   # Alternate D4/D5
        (20, 21), (21, 20),   # Alternate D6/D7
        (0, 1), (1, 0),       # Current UART pins
        (16, 17), (17, 16)    # User mentioned D6/D7
    ]
    
    found = False
    for sda, scl in pairs:
        try:
            i2c = machine.SoftI2C(sda=machine.Pin(sda), scl=machine.Pin(scl), freq=100000, timeout=200)
            devs = i2c.scan()
            if devs:
                print(f"!!! FOUND: {devs} on SDA={sda}, SCL={scl}")
                found = True
        except:
            pass
            
    if not found:
        print("Scanned all pairs. No devices found.")
    print("--- DONE ---")

if __name__ == "__main__":
    scan_all()
