/**
 * SensorSwarm I2C Leaf — ATtiny85/84/1614
 *
 * Minimal I2C slave that responds to Hub master reads with
 * swarm binary frames. Designed for <2KB RAM.
 *
 * Wiring:
 *   ATtiny SDA -> Hub SDA (with 4.7k pull-up)
 *   ATtiny SCL -> Hub SCL (with 4.7k pull-up)
 *   ATtiny VCC -> 3.3V (battery or Hub power)
 *
 * Build: PlatformIO with ATtiny framework
 */

#include <Arduino.h>
#include <Wire.h>

// ── Configuration ───────────────────────────────────────────

#define I2C_ADDR      0x10
#define LEAF_ID       20
#define HW_TYPE_ATTINY 0x03

// Swarm protocol constants
#define MAGIC         0x53
#define VERSION       0x01
#define MSG_SENSOR_REPORT 0x01
#define MSG_HEARTBEAT     0x02
#define MSG_REGISTER      0x04
#define MSG_COMMAND       0x80
#define MSG_ACK           0xFE

// Channel types
#define CH_TEMPERATURE    0x01
#define CH_HUMIDITY       0x02
#define CH_BATTERY_MV     0x0B

// ── Frame buffer ────────────────────────────────────────────

#define MAX_FRAME 32
static uint8_t tx_buf[MAX_FRAME];
static uint8_t tx_len = 0;

static uint8_t rx_buf[MAX_FRAME];
static volatile uint8_t rx_len = 0;
static volatile bool rx_ready = false;

// ── Checksum ────────────────────────────────────────────────

static uint8_t xor_checksum(const uint8_t *data, uint8_t len) {
    uint8_t cs = 0;
    for (uint8_t i = 0; i < len; i++) {
        cs ^= data[i];
    }
    return cs;
}

// ── Frame builder ───────────────────────────────────────────

static uint8_t build_frame(uint8_t msg_type, const uint8_t *payload,
                           uint8_t payload_len, uint8_t *out) {
    uint8_t pos = 0;
    out[pos++] = MAGIC;
    out[pos++] = VERSION;
    out[pos++] = msg_type;
    out[pos++] = LEAF_ID;
    for (uint8_t i = 0; i < payload_len; i++) {
        out[pos++] = payload[i];
    }
    out[pos] = xor_checksum(out, pos);
    pos++;
    return pos;
}

// ── Sensor reading ──────────────────────────────────────────

static float read_temperature() {
    // ATtiny internal temperature sensor (approximate)
    // For real use, connect an external sensor like DS18B20
    #if defined(__AVR_ATtiny85__) || defined(__AVR_ATtiny84__)
    // Read internal temp sensor
    ADMUX = 0x8F;  // Internal 1.1V ref, temp sensor
    delay(5);
    ADCSRA |= (1 << ADSC);
    while (ADCSRA & (1 << ADSC));
    int raw = ADC;
    return (float)(raw - 275) / 1.0;  // Rough calibration
    #else
    return 22.0;  // Placeholder for other platforms
    #endif
}

static uint16_t read_battery_mv() {
    // Read VCC using internal bandgap reference
    #if defined(__AVR_ATtiny85__) || defined(__AVR_ATtiny84__)
    ADMUX = 0x0C | (1 << REFS2);  // Bandgap vs VCC
    delay(5);
    ADCSRA |= (1 << ADSC);
    while (ADCSRA & (1 << ADSC));
    uint16_t raw = ADC;
    return (uint16_t)(1125300UL / raw);  // VCC in mV
    #else
    return 3300;
    #endif
}

// ── Build sensor report ─────────────────────────────────────

static void prepare_sensor_frame() {
    float temp = read_temperature();
    uint16_t batt = read_battery_mv();

    // Payload: N_channels(1B) + [ch_type(1B) + value(4B float)] * N
    uint8_t payload[12];  // 1 + 5 + 5 = 11 bytes for 2 channels
    uint8_t pos = 0;

    payload[pos++] = 2;  // 2 channels

    // Temperature
    payload[pos++] = CH_TEMPERATURE;
    memcpy(&payload[pos], &temp, 4);
    pos += 4;

    // Battery
    float batt_f = (float)batt;
    payload[pos++] = CH_BATTERY_MV;
    memcpy(&payload[pos], &batt_f, 4);
    pos += 4;

    tx_len = build_frame(MSG_SENSOR_REPORT, payload, pos, tx_buf);
}

// ── Build register frame ────────────────────────────────────

static void prepare_register_frame() {
    uint8_t payload[4];
    payload[0] = HW_TYPE_ATTINY;  // hw_type
    payload[1] = 2;               // N capabilities
    payload[2] = CH_TEMPERATURE;
    payload[3] = CH_BATTERY_MV;

    tx_len = build_frame(MSG_REGISTER, payload, 4, tx_buf);
}

// ── I2C callbacks ───────────────────────────────────────────

void onRequest() {
    // Hub is reading — send current frame
    Wire.write(tx_buf, tx_len);
}

void onReceive(int num_bytes) {
    // Hub is writing — receive command
    rx_len = 0;
    while (Wire.available() && rx_len < MAX_FRAME) {
        rx_buf[rx_len++] = Wire.read();
    }
    rx_ready = true;
}

// ── Main ────────────────────────────────────────────────────

static uint32_t last_report = 0;
static bool registered = false;

void setup() {
    Wire.begin(I2C_ADDR);
    Wire.onRequest(onRequest);
    Wire.onReceive(onReceive);

    // Prepare register frame as first response
    prepare_register_frame();
}

void loop() {
    uint32_t now = millis();

    // Process received commands
    if (rx_ready) {
        rx_ready = false;
        if (rx_len >= 5 && rx_buf[0] == MAGIC) {
            uint8_t msg_type = rx_buf[2];
            if (msg_type == MSG_COMMAND) {
                // Build ACK as next response
                tx_len = build_frame(MSG_ACK, NULL, 0, tx_buf);
                // Then prepare fresh sensor data
                delay(10);
                prepare_sensor_frame();
            }
        }
    }

    // Periodic sensor update (every 30s)
    if (now - last_report >= 30000UL || !registered) {
        prepare_sensor_frame();
        last_report = now;
        registered = true;
    }

    delay(100);
}
