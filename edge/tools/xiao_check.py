
import machine
import time

def check_uart(tx_pin, rx_pin):
    print(f"Checking UART TX={tx_pin}, RX={rx_pin}...")
    try:
        uart = machine.UART(1, baudrate=9600, tx=machine.Pin(tx_pin), rx=machine.Pin(rx_pin), timeout=1000)
        uart.write(b'\xff\x01\x86\x00\x00\x00\x00\x00\x79')
        time.sleep(0.5)
        if uart.any():
            data = uart.read()
            print(f"!!! UART RESPONSE !!! Data: {data}")
            return True
    except Exception as e:
        print(f"UART Error: {e}")
    return False

def check_i2c(sda_pin, scl_pin):
    print(f"Checking I2C SDA={sda_pin}, SCL={scl_pin}...")
    try:
        i2c = machine.I2C(0, sda=machine.Pin(sda_pin), scl=machine.Pin(scl_pin), freq=100000, timeout=1000)
        devs = i2c.scan()
        if devs:
            print(f"!!! I2C DEVICE FOUND !!! Addr: {devs}")
            return True
    except Exception as e:
        print(f"I2C Error: {e}")
    return False

print("--- STARTING XIAO C6 CHECK ---")
# UART checks (XIAO D6/D7 are 21/20)
check_uart(21, 20)
check_uart(20, 21)

# I2C checks (XIAO D4/D5 are 4/5? or 6/7?)
check_i2c(4, 5)
check_i2c(5, 4)
check_i2c(6, 7)
check_i2c(7, 6)

print("--- DONE ---")
