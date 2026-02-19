# 05. Edge Device Wiring Diagram

This document illustrates the connection of sensors and actuators to the ESP32-DevKitC-32E for the Office Sensor Node.

## 1. Office Sensor Node Wiring

```mermaid
graph TD
    subgraph Power
        USB[USB Power 5V]
        GND[Common Ground]
    end

    subgraph MCU [ESP32-DevKitC-32E]
        V3[3V3]
        V5[5V]
        GND_ESP[GND]
        D21[GPIO 21 (SDA)]
        D22[GPIO 22 (SCL)]
        D13[GPIO 13]
        D14[GPIO 14]
        D4[GPIO 4]
        D12[GPIO 12]
        D34[GPIO 34 (ADC)]
    end

    subgraph Sensors
        SHT[SHT31 Temp/Hum Sensor<br/>(I2C)]
        PIR[PaPIRs Motion Sensor]
        LIGHT[NJL7502L Light Sensor]
        IR_RX[IR Receiver OSRB38C9AA]
    end

    subgraph Actuators
        RELAY[5V Relay Module]
        IR_TX[IR LED 940nm]
    end

    %% Power Connections
    USB --> V5
    USB -.-> GND_ESP
    V3 --> SHT
    V3 --> PIR
    V3 --> LIGHT
    V3 --> IR_RX
    V5 --> RELAY

    %% Ground Connections
    GND_ESP -.-> SHT
    GND_ESP -.-> PIR
    GND_ESP -.-> LIGHT
    GND_ESP -.-> IR_RX
    GND_ESP -.-> RELAY
    GND_ESP -.-> IR_TX

    %% Data Connections
    D21 === SHT
    D22 === SHT
    
    PIR --> D13
    IR_RX --> D14
    LIGHT --> D34
    
    D12 --> RELAY
    D4 --> IR_TX
```

### Pin Assignment Table

| GPIO Pin | Function | Component | Notes |
| :--- | :--- | :--- | :--- |
| **21** | I2C SDA | SHT31 | Requires Pull-up (usually on module) |
| **22** | I2C SCL | SHT31 | Requires Pull-up (usually on module) |
| **13** | Digital In | PaPIRs Motion | Active High |
| **14** | Digital In | IR Receiver | Active Low |
| **34** | Analog In | Light Sensor | 10kΩ Pull-down required |
| **12** | Digital Out | Relay | Active High/Low depends on module |
| **4** | Digital Out | IR LED | Drive via Transistor (2N2222 etc) recommended for range |

### Circuit Notes
1.  **Light Sensor (NJL7502L)**: Connect the sensor in series with a 10kΩ resistor to create a voltage divider. Connect the junction to GPIO 34.
2.  **IR LED**: A single pin from ESP32 can drive an LED, but for better range, use a transistor (like 2SC1815) to switch the LED with higher current from the 5V rail.
3.  **Relay**: Most modules have a built-in transistor driver. Connect directly to GPIO.
