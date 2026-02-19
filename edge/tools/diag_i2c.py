
import machine
import time
print('I2C Scan Start on D4(22), D5(23)...')
try:
    # Use SoftI2C and lower frequency for stability
    # Use pull-ups explicitly as well
    sda = machine.Pin(22, machine.Pin.IN, machine.Pin.PULL_UP)
    scl = machine.Pin(23, machine.Pin.IN, machine.Pin.PULL_UP)
    i2c = machine.SoftI2C(sda=sda, scl=scl, freq=10000, timeout=100000)
    print('Scanning...')
    devices = i2c.scan()
    print('FOUND:', [hex(d) for d in devices])
except Exception as e:
    print('SCAN ERROR:', e)
print('Scan End.')
