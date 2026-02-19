from machine import UART
import time

class MHZ19C:
    def __init__(self, uart_id, rx_pin, tx_pin):
        self.uart = UART(uart_id, baudrate=9600, rx=rx_pin, tx=tx_pin, bits=8, parity=None, stop=1)
        time.sleep(1)

    def read_co2(self):
        # Command to read gas concentration: [0xFF, 0x01, 0x86, 0x00, 0x00, 0x00, 0x00, 0x00, 0x79]
        cmd = b'\xff\x01\x86\x00\x00\x00\x00\x00\x79'
        self.uart.write(cmd)
        time.sleep(0.1)
        
        if self.uart.any() >= 9:
            res = self.uart.read(9)
            if res[0] == 0xFF and res[1] == 0x86:
                checksum = self._checksum(res)
                if checksum == res[8]:
                    co2 = res[2] * 256 + res[3]
                    return co2
                else:
                    print("MH-Z19C checksum error")
        return None

    def _checksum(self, data):
        csum = 0
        for i in range(1, 8):
            csum += data[i]
        csum = 0xFF - (csum & 0xFF)
        csum += 1
        return csum & 0xFF
