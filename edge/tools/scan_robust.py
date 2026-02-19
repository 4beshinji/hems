
import machine
import time
def scan_safe():
    print("Starting robust scan...")
    # Pin list from XIAO C6 datasheet search (0,1,2,3,22,23,16,17,18,19,20)
    pins = [0, 1, 2, 3, 22, 23, 16, 17, 18, 19, 20, 6, 7]
    for sda in pins:
        for scl in pins:
            if sda == scl: continue
            try:
                # Use SoftI2C to avoid hardware lockups
                # Use pull-up just in case
                i2c = machine.SoftI2C(sda=machine.Pin(sda, machine.Pin.PULL_UP), 
                                      scl=machine.Pin(scl, machine.Pin.PULL_UP), 
                                      timeout=100000)
                res = i2c.scan()
                if res:
                    print(f"FOUND! SDA={sda}, SCL={scl}, Addr={[hex(d) for d in res]}")
            except Exception as e:
                pass
    print("Scan finished.")

scan_safe()
