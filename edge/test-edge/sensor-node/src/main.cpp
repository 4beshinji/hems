/**
 * Sensor Node - XIAO ESP32-S3 + BME680
 *
 * Features:
 * - BME680 environmental data (temperature, humidity, pressure, gas)
 * - Wi-Fi/MQTT connection
 * - Per-channel telemetry compatible with WorldModel
 * - MCP tool support (JSON-RPC 2.0) for get_status
 */

#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME680.h>

// ==================== Configuration ====================
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

const char* MQTT_SERVER = "192.168.128.161";
const int MQTT_PORT = 1883;
const char* DEVICE_ID = "sensor_node_01";

// MQTT topics (per-channel for WorldModel compatibility)
const char* TOPIC_PREFIX = "office/meeting_room_a/sensor/sensor_node_01";
const char* TOPIC_MCP_REQUEST = "mcp/sensor_node_01/request/call_tool";

// I2C pins (XIAO ESP32-S3)
#define SDA_PIN 5
#define SCL_PIN 6

// BME680 I2C address
#define BME680_I2C_ADDR 0x76

// Telemetry interval (milliseconds)
#define TELEMETRY_INTERVAL 10000  // 10 seconds

// ==================== Globals ====================
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
Adafruit_BME680 bme;

unsigned long lastTelemetry = 0;
unsigned long lastStatus = 0;

// Forward declarations
void mqttCallback(char* topic, byte* payload, unsigned int length);
void handleToolCall(JsonDocument& doc);
void readAndPublishSensors();
void publishStatus();

// ==================== Setup ====================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n=== Sensor Node Starting ===");

  // I2C init
  Wire.begin(SDA_PIN, SCL_PIN);

  // BME680 init
  Serial.println("Initializing BME680...");
  if (!bme.begin(BME680_I2C_ADDR, &Wire)) {
    Serial.println("Could not find BME680! Check wiring (0x76 or 0x77)");
    while (1) delay(1000);
  }
  bme.setTemperatureOversampling(BME680_OS_8X);
  bme.setHumidityOversampling(BME680_OS_2X);
  bme.setPressureOversampling(BME680_OS_4X);
  bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
  bme.setGasHeater(320, 150);
  Serial.println("BME680 initialized");

  // WiFi
  Serial.print("Connecting to WiFi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nWiFi connected: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\nWiFi failed!");
    ESP.restart();
  }

  // MQTT
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(2048);

  Serial.print("Connecting to MQTT...");
  attempts = 0;
  while (!mqtt.connected() && attempts < 5) {
    if (mqtt.connect(DEVICE_ID)) {
      mqtt.subscribe(TOPIC_MCP_REQUEST);
      Serial.printf("\nMQTT connected, subscribed: %s\n", TOPIC_MCP_REQUEST);
    } else {
      Serial.print(".");
      delay(2000);
      attempts++;
    }
  }
  if (!mqtt.connected()) {
    Serial.println("\nMQTT connection failed!");
  }

  Serial.println("=== Initialization Complete ===\n");
  publishStatus();
}

// ==================== Main Loop ====================
void loop() {
  // MQTT reconnect
  if (!mqtt.connected()) {
    Serial.println("MQTT disconnected, reconnecting...");
    if (mqtt.connect(DEVICE_ID)) {
      mqtt.subscribe(TOPIC_MCP_REQUEST);
      Serial.println("MQTT reconnected");
    } else {
      delay(2000);
      return;
    }
  }
  mqtt.loop();

  // Periodic telemetry
  if (millis() - lastTelemetry > TELEMETRY_INTERVAL) {
    readAndPublishSensors();
    lastTelemetry = millis();
  }

  // Periodic status (every 30s)
  if (millis() - lastStatus > 30000) {
    publishStatus();
    lastStatus = millis();
  }

  delay(10);
}

// ==================== MQTT Callback ====================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, payload, length);
  if (error) {
    Serial.printf("JSON parse error: %s\n", error.c_str());
    return;
  }

  // MCP tool call
  if (strcmp(topic, TOPIC_MCP_REQUEST) == 0) {
    handleToolCall(doc);
  }
}

// ==================== MCP Tool Handler ====================
void handleToolCall(JsonDocument& doc) {
  const char* reqId = doc["id"] | "unknown";
  const char* method = doc["method"] | "";

  if (strcmp(method, "call_tool") != 0) return;

  const char* toolName = doc["params"]["name"] | "";
  Serial.printf("Tool call: %s (id=%s)\n", toolName, reqId);

  // Build response
  JsonDocument response;
  response["jsonrpc"] = "2.0";
  response["id"] = reqId;

  if (strcmp(toolName, "get_status") == 0) {
    // Read sensors and return
    if (bme.performReading()) {
      JsonObject result = response["result"].to<JsonObject>();
      result["temperature"] = bme.temperature;
      result["humidity"] = bme.humidity;
      result["pressure"] = bme.pressure / 100.0;
      result["gas_resistance"] = bme.gas_resistance / 1000.0;
      result["uptime_sec"] = millis() / 1000;
      result["free_heap"] = ESP.getFreeHeap();
    } else {
      response["error"] = "Failed to read BME680";
    }
  } else {
    response["error"] = "Unknown tool";
  }

  // Publish response
  char responseTopic[128];
  snprintf(responseTopic, sizeof(responseTopic), "mcp/%s/response/%s", DEVICE_ID, reqId);

  String output;
  serializeJson(response, output);
  mqtt.publish(responseTopic, output.c_str());
  Serial.printf("Response sent: %s\n", responseTopic);
}

// ==================== Sensor Read & Publish ====================
void readAndPublishSensors() {
  if (!bme.performReading()) {
    Serial.println("Failed to perform reading");
    return;
  }

  float temperature = bme.temperature;
  float humidity = bme.humidity;
  float pressure = bme.pressure / 100.0;  // Pa to hPa
  float gas = bme.gas_resistance / 1000.0;  // Ohms to kOhms

  Serial.printf("T=%.1f°C H=%.1f%% P=%.1fhPa G=%.1fkΩ\n",
                temperature, humidity, pressure, gas);

  // Per-channel telemetry with {"value": X} format for WorldModel
  char topic[128];
  char payload[64];

  snprintf(topic, sizeof(topic), "%s/temperature", TOPIC_PREFIX);
  snprintf(payload, sizeof(payload), "{\"value\":%.2f}", temperature);
  mqtt.publish(topic, payload);

  snprintf(topic, sizeof(topic), "%s/humidity", TOPIC_PREFIX);
  snprintf(payload, sizeof(payload), "{\"value\":%.2f}", humidity);
  mqtt.publish(topic, payload);

  snprintf(topic, sizeof(topic), "%s/pressure", TOPIC_PREFIX);
  snprintf(payload, sizeof(payload), "{\"value\":%.2f}", pressure);
  mqtt.publish(topic, payload);

  snprintf(topic, sizeof(topic), "%s/gas", TOPIC_PREFIX);
  snprintf(payload, sizeof(payload), "{\"value\":%.2f}", gas);
  mqtt.publish(topic, payload);
}

// ==================== Status Publish ====================
void publishStatus() {
  char topic[128];
  snprintf(topic, sizeof(topic), "%s/heartbeat", TOPIC_PREFIX);

  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["status"] = "online";
  doc["uptime_sec"] = millis() / 1000;
  doc["free_heap"] = ESP.getFreeHeap();
  doc["wifi_rssi"] = WiFi.RSSI();

  String output;
  serializeJson(doc, output);
  mqtt.publish(topic, output.c_str());
}
