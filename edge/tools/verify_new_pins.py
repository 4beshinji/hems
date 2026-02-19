
import machine
import time

def verify_setup():
    print("--- VERIFYING NEW WIRING ---")
    
    # 1. I2C on D2(SDA=2), D3(SCL=3)
    print("Checking I2C (SDA=2, SCL=3)...", end="")
    try:
        i2c = machine.I2C(0, sda=machine.Pin(2), scl=machine.Pin(3), freq=100000)
        devs = i2c.scan()
        if devs:
            print(f" FOUND! Devices: {devs}")
            # Try to read ID if 0x77/0x76 to confirm BME680
            if 0x76 in devs or 0x77 in devs:
                print("  -> BME680 detected!")
        else:
            print(" [] (No devices)")
    except Exception as e:
        print(f" Error: {e}")

    # 2. UART on D0(TX=0), D1(RX=1)
    # Note: ESP TX=0 connects to Sensor RX. ESP RX=1 connects to Sensor TX.
    print("Checking UART (TX=0, RX=1) for MH-Z19C...", end="")
    try:
        # Stop any previous UART usage if possible? No need, we re-init.
        uart = machine.UART(1, baudrate=9600, tx=machine.Pin(0), rx=machine.Pin(1), timeout=1000)
        # Send command to read CO2
        uart.write(b'\xff\x01\x86\x00\x00\x00\x00\x00\x79')
        time.sleep(1.0) # Wait for response
        if uart.any():
            data = uart.read()
            print(f" RESPONSE: {data}")
            if len(data) == 9 and data[0] == 0xff and data[1] == 0x86:
                high = data[2]
                low = data[3]
                co2 = (high << 8) + low
                print(f"  -> MH-Z19C detected! CO2: {co2} ppm")
            else:
                 print("  -> Received data but unexpected format.")
        else:
            print(" None (No response)")
    except Exception as e:
        print(f" Error: {e}")

    print("--- DONE ---")

if __name__ == "__main__":
    verify_setup()
