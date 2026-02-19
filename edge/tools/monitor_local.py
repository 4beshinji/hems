
import machine
import time
from bme680_driver import BME680_I2C

print('--- LOCAL SENSOR MONITOR (NO WIFI) ---')
# Using the verified pins from the diagnostic test
I2C_SDA_PIN = 23 # D5
I2C_SCL_PIN = 22 # D4

i2c = machine.SoftI2C(sda=machine.Pin(I2C_SDA_PIN, machine.Pin.PULL_UP), 
                      scl=machine.Pin(I2C_SCL_PIN, machine.Pin.PULL_UP), 
                      freq=100000, timeout=100000)

devices = i2c.scan()
print('I2C Scan:', [hex(d) for d in devices])

if 0x77 in devices:
    bme = BME680_I2C(i2c, address=0x77)
    print('BME680 Initialized.')
    while True:
        try:
            data = bme.read_sensor()
            print('TELEMETRY:', data)
            time.sleep(2)
        except Exception as e:
            print('Read Error:', e)
            time.sleep(2)
else:
    print('SENSOR NOT FOUND at 0x77')
