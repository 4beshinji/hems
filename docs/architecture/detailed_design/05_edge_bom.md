# 05. Edge Device Bill of Materials (BOM)

This document lists the components required for the Edge Layer of the Symbiotic Office Management System (SOMS). The selection prioritizes availability at **Akizuki Denshi** (Japan) as requested.

## 1. Office Environmental Sensor Node
This node is responsible for monitoring temperature, humidity, occupancy, and controlling lighting/infrared devices.

### 1.1 Core Components (Akizuki Denshi)

| Component Type | Part Name | Manufacturer | Akizuki Code | Price (Approx.) | Qty/Unit | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Microcontroller** | ESP32-DevKitC-32E | Espressif | [M-15673](https://akizukidenshi.com/catalog/g/gM-15673/) | ¥1,480 | 1 | Standard development board with Wi-Fi/BT. |
| **Temp/Hum Sensor** | SHT31 Module (Grove) | Seeed Studio | [M-14125](https://akizukidenshi.com/catalog/g/gM-14125/) | ¥1,200 | 1 | High precision I2C sensor. |
| **Motion Sensor** | PaPIRs Motion Sensor (WZ) | Panasonic | [I-07616](https://akizukidenshi.com/catalog/g/gI-07616/) | ¥600 | 1 | High reliability PIR sensor. |
| **Light Sensor** | NJL7502L | New Japan Radio | [I-02325](https://akizukidenshi.com/catalog/g/gI-02325/) | ¥40 | 1 | Simple phototransistor for ambient light. |
| **IR LED** | 5mm IR LED 940nm | OptoSupply | [I-03261](https://akizukidenshi.com/catalog/g/gI-03261/) | ¥100 (10pcs) | 1 | For controlling legacy AC/TV. |
| **IR Receiver** | OSRB38C9AA | OptoSupply | [I-04663](https://akizukidenshi.com/catalog/g/gI-04663/) | ¥100 (5pcs) | 1 | For learning IR codes. |
| **Relay Module** | 5V Relay Module | Akizuki Original | [K-11245](https://akizukidenshi.com/catalog/g/gK-11245/) | ¥450 | 1 | For physical device control (Lights/Fan). |
| **Resistors** | 1/4W Carbon Resistors | Various | R-25*** | ¥100 (100pcs) | Various | 330Ω (for IR LED), 10kΩ (Pull-ups). |
| **Breadboard** | Solderless Breadboard | Generic | [P-00315](https://akizukidenshi.com/catalog/g/gP-00315/) | ¥250 | 1 | For prototyping. |
| **Jumper Wires** | Jumper Wire Set | Generic | [C-05159](https://akizukidenshi.com/catalog/g/gC-05159/) | ¥400 | 1 | |

**Total Estimated Cost (Office Node): ¥4,000 - ¥5,000**

---

## 2. Water Management Node (Hydroponics/Aquarium)
This node requires specialized sensors for water quality which are generally **not available** at Akizuki Denshi. Alternative sources (Amazon JP / Switch Science) are listed where necessary.

### 2.1 Core Components (Mixed Sourcing)

| Component Type | Part Name | Akizuki Code | Source | Price (Approx.) | Qty | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Microcontroller** | ESP32-DevKitC-32E | [M-15673](https://akizukidenshi.com/catalog/g/gM-15673/) | Akizuki | ¥1,480 | 1 | Same as Office Node. |
| **ADC Module** | ADS1115 (16-bit 4-ch) | - | Amazon/Switch Science | ¥800 | 1 | For reading analog pH/EC sensors. |
| **Water Temp** | DS18B20 (Waterproof) | - | Amazon/Switch Science | ¥500 | 1 | Waterproof probe type. |
| **pH Sensor** | Analog pH Meter Kit | - | Amazon/Switch Science | ¥3,500 | 1 | Probe + Signal Board. |
| **EC Sensor** | Analog TDS/EC Meter | - | Amazon/Switch Science | ¥2,000 | 1 | Probe + Signal Board. |
| **Relay Module** | 4-ch 5V Relay Module | - | Amazon/Switch Science | ¥800 | 1 | For Pumps/Heaters. |
| **Pumps** | 12V Peristaltic Pump | - | Amazon/Switch Science | ¥1,500 | 2 | For pH Down / Fertilizer. |

**Total Estimated Cost (Water Node): ¥10,000 - ¥12,000**

### 2.2 Why non-Akizuki parts?
-   **Waterproof DS18B20**: Akizuki sells the bare DS18B20 chip, but not the waterproof probe version required for liquids.
-   **pH/EC Sensors**: Akizuki does not stock industrial or hobbyist chemical sensors.
-   **Peristaltic Pumps**: Specific dosing pumps are not part of Akizuki's standard catalog.

## 3. Tools & Consumables
-   **USB Cable**: Micro-USB data cable (for ESP32 programming & power).
-   **USB Power Supply**: 5V 2A adapter.
