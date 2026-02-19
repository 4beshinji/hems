/**
 * Camera Node - Freenove ESP32 WROVER v3.0
 * MCP-compliant Request-Driven Image Server
 *
 * Features:
 * - JSON-RPC 2.0 MCP protocol via mcp/{device_id}/request/call_tool
 * - Dynamic resolution JPEG capture on demand
 * - Base64-encoded image delivery over MQTT
 * - Periodic heartbeat
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <base64.h>
#include "esp_camera.h"

// ==================== Configuration ====================
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* MQTT_SERVER = "192.168.128.161";
const int MQTT_PORT = 1883;
const char* DEVICE_ID = "camera_node_01";

// MCP topic (JSON-RPC 2.0 standard)
#define TOPIC_MCP_REQUEST "mcp/camera_node_01/request/call_tool"
#define TOPIC_STATUS "office/camera/camera_node_01/status"

// Camera pins (Freenove ESP32 WROVER v3.0)
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     21
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       19
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       5
#define Y2_GPIO_NUM       4
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22
#define LED_PIN           2

// ==================== Globals ====================
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
sensor_t* camera_sensor = nullptr;

// ==================== Resolution Mapping ====================
framesize_t parseResolution(const char* resStr) {
  if (strcmp(resStr, "QVGA") == 0) return FRAMESIZE_QVGA;   // 320x240
  if (strcmp(resStr, "VGA") == 0) return FRAMESIZE_VGA;      // 640x480
  if (strcmp(resStr, "SVGA") == 0) return FRAMESIZE_SVGA;    // 800x600
  if (strcmp(resStr, "XGA") == 0) return FRAMESIZE_XGA;      // 1024x768
  if (strcmp(resStr, "UXGA") == 0) return FRAMESIZE_UXGA;    // 1600x1200
  return FRAMESIZE_VGA;
}

// ==================== Camera Init ====================
void setupCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 10;
  config.fb_count = psramFound() ? 2 : 1;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    ESP.restart();
  }

  camera_sensor = esp_camera_sensor_get();
  Serial.printf("Camera initialized (PSRAM: %s)\n", psramFound() ? "YES" : "NO");
}

// ==================== WiFi ====================
void setupWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.print("Connecting to WiFi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts++ < 20) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nWiFi connected: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\nWiFi failed!");
    ESP.restart();
  }
}

// ==================== MQTT ====================
void mqttCallback(char* topic, byte* payload, unsigned int length);

void setupMQTT() {
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(65536);

  Serial.print("Connecting to MQTT");
  while (!mqtt.connected()) {
    if (mqtt.connect(DEVICE_ID)) {
      mqtt.subscribe(TOPIC_MCP_REQUEST);
      Serial.printf("\nMQTT connected, subscribed: %s\n", TOPIC_MCP_REQUEST);
    } else {
      Serial.print(".");
      delay(2000);
    }
  }
}

// ==================== MCP Tool Handler ====================
void handleCaptureToolCall(const char* reqId, JsonObject args) {
  const char* resolution = args["resolution"] | "VGA";
  int quality = args["quality"] | 10;

  Serial.printf("Capture: id=%s, res=%s, q=%d\n", reqId, resolution, quality);
  digitalWrite(LED_PIN, LOW);

  // Set resolution
  framesize_t framesize = parseResolution(resolution);
  camera_sensor->set_framesize(camera_sensor, framesize);
  camera_sensor->set_quality(camera_sensor, quality);

  // Capture
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Capture failed!");
    digitalWrite(LED_PIN, HIGH);

    // Send error response
    JsonDocument response;
    response["jsonrpc"] = "2.0";
    response["error"] = "Capture failed";
    response["id"] = reqId;

    char responseTopic[128];
    snprintf(responseTopic, sizeof(responseTopic), "mcp/%s/response/%s", DEVICE_ID, reqId);
    String output;
    serializeJson(response, output);
    mqtt.publish(responseTopic, output.c_str());
    return;
  }

  Serial.printf("Captured: %dx%d, %u bytes\n", fb->width, fb->height, fb->len);

  // Base64 encode
  String base64Image = base64::encode(fb->buf, fb->len);

  // Build JSON-RPC 2.0 response
  JsonDocument response;
  response["jsonrpc"] = "2.0";
  response["id"] = reqId;
  JsonObject result = response["result"].to<JsonObject>();
  result["image"] = base64Image;
  result["width"] = fb->width;
  result["height"] = fb->height;
  result["size_bytes"] = fb->len;
  result["format"] = "jpeg";

  // Publish response
  char responseTopic[128];
  snprintf(responseTopic, sizeof(responseTopic), "mcp/%s/response/%s", DEVICE_ID, reqId);

  String output;
  serializeJson(response, output);

  bool sent = mqtt.publish(responseTopic, output.c_str());
  Serial.printf("Response sent: %s (%s)\n", responseTopic, sent ? "OK" : "FAIL");

  esp_camera_fb_return(fb);
  digitalWrite(LED_PIN, HIGH);
}

void handleGetStatus(const char* reqId) {
  JsonDocument response;
  response["jsonrpc"] = "2.0";
  response["id"] = reqId;
  JsonObject result = response["result"].to<JsonObject>();
  result["device_id"] = DEVICE_ID;
  result["status"] = "online";
  result["uptime_sec"] = millis() / 1000;
  result["free_heap"] = ESP.getFreeHeap();
  result["wifi_rssi"] = WiFi.RSSI();
  result["psram"] = psramFound();

  char responseTopic[128];
  snprintf(responseTopic, sizeof(responseTopic), "mcp/%s/response/%s", DEVICE_ID, reqId);

  String output;
  serializeJson(response, output);
  mqtt.publish(responseTopic, output.c_str());
}

// ==================== MQTT Callback ====================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, payload, length);

  if (error) {
    Serial.printf("JSON parse error: %s\n", error.c_str());
    return;
  }

  // Verify JSON-RPC 2.0 call_tool method
  const char* method = doc["method"] | "";
  if (strcmp(method, "call_tool") != 0) return;

  const char* reqId = doc["id"] | "unknown";
  const char* toolName = doc["params"]["name"] | "";
  JsonObject args = doc["params"]["arguments"].as<JsonObject>();

  Serial.printf("Tool call: %s (id=%s)\n", toolName, reqId);

  if (strcmp(toolName, "capture") == 0) {
    handleCaptureToolCall(reqId, args);
  } else if (strcmp(toolName, "get_status") == 0) {
    handleGetStatus(reqId);
  } else {
    // Unknown tool error
    JsonDocument response;
    response["jsonrpc"] = "2.0";
    response["error"] = "Unknown tool";
    response["id"] = reqId;

    char responseTopic[128];
    snprintf(responseTopic, sizeof(responseTopic), "mcp/%s/response/%s", DEVICE_ID, reqId);
    String output;
    serializeJson(response, output);
    mqtt.publish(responseTopic, output.c_str());
  }
}

// ==================== Heartbeat ====================
void publishStatus() {
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["status"] = "online";
  doc["uptime_sec"] = millis() / 1000;
  doc["free_heap"] = ESP.getFreeHeap();
  doc["wifi_rssi"] = WiFi.RSSI();

  String output;
  serializeJson(doc, output);
  mqtt.publish(TOPIC_STATUS, output.c_str());
}

// ==================== Setup ====================
void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.println("\n=== Camera Node (MCP-compliant) ===");

  setupCamera();
  setupWiFi();
  setupMQTT();

  digitalWrite(LED_PIN, HIGH);
  publishStatus();

  Serial.println("=== Ready ===\n");
}

// ==================== Main Loop ====================
void loop() {
  if (!mqtt.connected()) {
    Serial.println("MQTT reconnecting...");
    setupMQTT();
  }
  mqtt.loop();

  // Status every 30 seconds
  static unsigned long lastStatus = 0;
  if (millis() - lastStatus > 30000) {
    publishStatus();
    lastStatus = millis();
  }

  delay(10);
}
