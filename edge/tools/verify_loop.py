
import machine
import time

def verify_loop():
    print("--- WAITING FOR NEW MODULE (D2/D3) ---")
    print("  I2C: SDA->D2, SCL->D3 (Internal Pull-up Enabled for safety)")
    print("  UART: TX->D1, RX->D0")
    
    while True:
        try:
            # 1. I2C Check (D2/D3)
            # Use PULL_UP just in case user forgot external ones on new module
            i2c = machine.SoftI2C(sda=machine.Pin(2, machine.Pin.PULL_UP), 
                                  scl=machine.Pin(3, machine.Pin.PULL_UP), 
                                  freq=100000, timeout=500)
            devs = i2c.scan()
            if devs:
                print(f"\n!!! I2C DEVICE FOUND: {devs} !!!")
            else:
                print(".", end="")
            
            # 2. UART Check (D0/D1) - Just to confirm system is alive
            uart = machine.UART(1, baudrate=9600, tx=machine.Pin(0), rx=machine.Pin(1), timeout=200)
            uart.write(b'\xff\x01\x86\x00\x00\x00\x00\x00\x79')
            # Don't wait long, just check
            
        except Exception as e:
            # print(f"Exc: {e}")
            pass
        
        time.sleep(1)

if __name__ == "__main__":
    verify_loop()
