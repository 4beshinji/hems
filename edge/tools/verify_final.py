
import machine
import time

def check_i2c(sda, scl):
    print(f"Checking I2C SDA={sda}, SCL={scl}...", end="")
    try:
        i2c = machine.I2C(0, sda=machine.Pin(sda, machine.Pin.PULL_UP), scl=machine.Pin(scl, machine.Pin.PULL_UP), freq=100000)
        devs = i2c.scan()
        if devs:
            print(f" FOUND! {devs}")
        else:
            print(" []")
    except Exception as e:
        print(f" Err: {e}")

def check_uart(tx, rx):
    print(f"Checking UART TX={tx}, RX={rx}...", end="")
    try:
        uart = machine.UART(1, baudrate=9600, tx=machine.Pin(tx), rx=machine.Pin(rx), timeout=1000)
        uart.write(b'\xff\x01\x86\x00\x00\x00\x00\x00\x79')
        time.sleep(0.5)
        if uart.any():
            print(f" RESPONSE: {uart.read()}")
        else:
            print(" None")
    except Exception as e:
        print(f" Err: {e}")

print("--- FINAL CHECK ---")
check_i2c(22, 23)
check_i2c(23, 22)
check_i2c(4, 5) # Just in case

check_uart(16, 17)
check_uart(17, 16)
print("--- DONE ---")
