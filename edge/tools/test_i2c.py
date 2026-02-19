
import machine
import time
i2c = machine.I2C(0, sda=machine.Pin(22), scl=machine.Pin(23), freq=100000)
print('Scanning I2C on 22,23...')
devices = i2c.scan()
print('Devices found:', [hex(d) for d in devices])
