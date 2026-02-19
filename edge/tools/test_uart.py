
from machine import UART, Pin
import time

print('Testing UART1 for CO2 sensor...')
# D6=16, D7=17
# Try standard
uart = UART(1, baudrate=9600, tx=Pin(16), rx=Pin(17), timeout=1000)
cmd = b'\xff\x01\x86\x00\x00\x00\x00\x00\x79'

for i in range(3):
    print(f'Attempt {i+1}...')
    uart.write(cmd)
    time.sleep(0.5)
    if uart.any():
        print('Recv:', uart.read())
    else:
        print('No data recv.')
