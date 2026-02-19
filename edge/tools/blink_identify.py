
import machine
import time

def blink_pin(pin_num):
    print(f"\n>>> BLINKING GPIO {pin_num} <<<")
    try:
        p = machine.Pin(pin_num, machine.Pin.OUT)
        for _ in range(6):
            p.value(1)
            time.sleep(0.3)
            p.value(0)
            time.sleep(0.3)
        return True
    except Exception as e:
        print(f"Failed to blink GPIO {pin_num}: {e}")
        return False

def main():
    print("STARTING PIN IDENTIFICATION SEQUENCE")
    print("Watch the LED or use a voltmeter/LED on pins.")
    
    # Order: Onboard LED first to confirm operation
    blink_pin(15) # Yellow LED on XIAO
    
    # Then iterate common pins
    scan_pins = [0, 1, 2, 3, 4, 5, 6, 7, 20, 21, 22, 23]
    
    for p in scan_pins:
        blink_pin(p)
        time.sleep(1)
        
    print("SEQUENCE COMPLETE")

if __name__ == "__main__":
    main()
