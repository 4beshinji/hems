
import machine
import time
from bme680_driver import BME680_I2C

print('Testing BME680 locally...')
i2c = machine.SoftI2C(sda=machine.Pin(23), scl=machine.Pin(22), freq=100000)
try:
    bme = BME680_I2C(i2c, address=0x77)
    print('BME680 Initialized.')
    for _ in range(5):
        data = bme.read_sensor()
        print('Data:', data)
        time.sleep(2)
except Exception as e:
    print('Error:', e)
