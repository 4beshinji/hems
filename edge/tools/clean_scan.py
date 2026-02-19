
import machine
import time

def scan_i2c():
    print("Starting I2C Scan...")
    
    # Priority pairs
    pairs = [
        (6, 7), (7, 6),
        (4, 5), (5, 4),
        (2, 3), (3, 2),
        (22, 23), (23, 22),
        (20, 21), (21, 20),
        (0, 1), (1, 0),
        (15, 16), (16, 15)
    ]
    
    for sda, scl in pairs:
        try:
            i2c = machine.I2C(0, sda=machine.Pin(sda), scl=machine.Pin(scl), freq=100000, timeout=1000)
            devs = i2c.scan()
            if devs:
                print(f"!!! FOUND DEVICES: {devs} at SDA={sda}, SCL={scl} !!!")
                return
            else:
                pass
                # print(f"Checked SDA={sda}, SCL={scl}: No devices")
        except Exception as e:
            pass
            
    print("Scan complete. No devices found.")

if __name__ == "__main__":
    scan_i2c()
