# SOMS Sensor Node Enclosure v1.0

Parametric 3D-printable enclosure for the SOMS environmental sensor node.

## Target Hardware

| Component | Model | Role |
|-----------|-------|------|
| MCU | XIAO ESP32-C6 | WiFi 6, MCP/MQTT |
| Temp/Humidity/VOC | BME680 | I2C |
| CO₂ | MH-Z19C | UART (NDIR) |
| PIR (optional) | AM312 or HC-SR501 | GPIO |
| Fan (optional) | 25mm 5V | Forced exhaust |
| Connectors | JST-XH 2.5mm | Detachable wiring |

## Structure

```
┌─────────────────┐
│  Exhaust (top)   │  ← Hex vent / fan mount
├─────────────────┤
│  MCU Chamber     │  ← XIAO ESP32-C6
│  (upper)         │     Heat rises → exits top
├━━━━━━━━━━━━━━━━━┤  ← Thermal barrier (3mm solid + 5mm air gap)
│  Sensor Chamber  │  ← BME680 + MH-Z19C
│  (lower)         │     Cool air intake from below
├─────────────────┤
│  Intake (bottom) │  ← Side louvers
└─────────────────┘
     USB-C cable
```

## Parts (STL Export)

Change `part` variable in `enclosure.scad`:

| part | Description | Print orientation |
|------|-------------|-------------------|
| `"bottom"` | Sensor chamber + barrier | As-is (flat bottom on bed) |
| `"top"` | MCU chamber (no fan) | Auto-flipped (ceiling on bed) |
| `"top_fan"` | MCU chamber + 25mm fan | Auto-flipped |
| `"shell"` | Decorative outer cover | As-is |
| `"pir_am312"` | PIR insert for AM312 | As-is |
| `"pir_hcsr501"` | PIR insert for HC-SR501 | As-is |
| `"pir_blank"` | Blank cap (no PIR) | As-is |
| `"assembly"` | Visual check (exploded view) | — |

## Dimensions

| | Width | Depth | Height |
|---|---|---|---|
| Chassis (no fan) | 55.2mm | 33.2mm | 50.2mm |
| Chassis (with fan) | 55.2mm | 33.2mm | 59.2mm |
| Outer shell | 66.4mm | 44.4mm | 64.2mm |

## Print Settings

- **Material**: PETG recommended (heat resistance + flexibility)
- **Nozzle**: 0.4mm
- **Layer**: 0.2mm
- **Wall**: 4 perimeters (= 1.6mm)
- **Infill**: 20% gyroid
- **Supports**: Not required (designed for supportless printing)

## Assembly

1. Press M2 heat-set inserts into bottom half barrier (4x)
2. Wire sensors with JST-XH connectors
3. Mount MH-Z19C and BME680 in sensor chamber
4. Mount XIAO ESP32-C6 on rails in MCU chamber
5. Connect inter-chamber XH-8P harness through barrier
6. Join halves with M2×10 screws (through standoffs into inserts)
7. Insert PIR adapter (AM312/HC-SR501/blank)
8. Slide outer shell over chassis

## Wiring (JST-XH)

### Inter-chamber harness (XH-8P)

| Pin | Signal | Color (suggested) |
|-----|--------|-------------------|
| 1 | 3V3 | Red |
| 2 | GND | Black |
| 3 | SDA (I2C) | Blue |
| 4 | SCL (I2C) | Yellow |
| 5 | UART TX (CO₂) | Green |
| 6 | UART RX (CO₂) | White |
| 7 | PIR OUT | Orange |
| 8 | Reserved | — |
