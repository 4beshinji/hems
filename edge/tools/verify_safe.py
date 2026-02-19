
import machine
import time

print("--- SAFE VERIFY START ---")
time.sleep(1)

# I2C Check - D2/D3 (SoftI2C)
print("Checking I2C (SDA=2, SCL=3)...", end="")
try:
    i2c = machine.SoftI2C(sda=machine.Pin(2), scl=machine.Pin(3), freq=100000, timeout=1000)
    devs = i2c.scan()
    print(f" FOUND: {devs}")
except Exception as e:
    print(f" ERROR: {e}")

# UART Check - D0/D1 (TX=0, RX=1) -> Sensor RX=0, TX=1? Wait, TX connects to RX.
# ESP TX=0 -> Sensor RX. ESP RX=1 -> Sensor TX.
print("Checking UART (TX=0, RX=1)...", end="")
try:
    uart = machine.UART(1, baudrate=9600, tx=machine.Pin(0), rx=machine.Pin(1), timeout=1000)
    uart.write(b'\xff\x01\x86\x00\x00\x00\x00\x00\x79')
    time.sleep(1)
    if uart.any():
        print(f" RESPONSE: {uart.read()}")
    else:
        print(" NO RESPONSE")
except Exception as e:
    print(f" ERROR: {e}")

# UART Check - D0/D1 (TX=1, RX=0) -> Swapped
print("Checking UART (TX=1, RX=0)...", end="")
try:
    uart2 = machine.UART(1, baudrate=9600, tx=machine.Pin(1), rx=machine.Pin(0), timeout=1000)
    uart2.write(b'\xff\x01\x86\x00\x00\x00\x00\x00\x79')
    time.sleep(1)
    if uart2.any():
        print(f" RESPONSE: {uart2.read()}")
    else:
        print(" NO RESPONSE")
except Exception as e:
    print(f" ERROR: {e}")

print("--- SAFE VERIFY END ---")
