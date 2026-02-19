#!/usr/bin/env python3
"""
Camera Node Simulator - テスト用のカメラノードシミュレータ
実際のESP32がなくてもVision Serviceをテストできる
"""
import os
import paho.mqtt.client as mqtt
import json
import base64
import time
import sys
from PIL import Image
import io

class CameraNodeSimulator:
    def __init__(self, device_id="camera_node_01", broker="localhost", port=1883):
        self.device_id = device_id
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqtt_user = os.getenv("MQTT_USER")
        mqtt_pass = os.getenv("MQTT_PASS")
        if mqtt_user:
            self.client.username_pw_set(mqtt_user, mqtt_pass)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
    def on_connect(self, client, userdata, flags, rc, properties):
        print(f"Connected to MQTT broker (rc={rc})")
        request_topic = f"mcp/{self.device_id}/request/capture"
        client.subscribe(request_topic)
        print(f"Subscribed to: {request_topic}")
        
        # ステータス送信
        self.publish_status()
        
    def on_message(self, client, userdata, msg):
        print(f"\n[REQUEST] Topic: {msg.topic}")
        try:
            request = json.loads(msg.payload)
            print(f"Request: {json.dumps(request, indent=2)}")
            
            req_id = request.get("id", "unknown")
            resolution = request.get("resolution", "VGA")
            quality = request.get("quality", 10)
            
            # ダミー画像生成
            image = self.generate_dummy_image(resolution)
            
            # レスポンス送信
            self.send_response(req_id, image, resolution)
            
        except Exception as e:
            print(f"Error handling request: {e}")
    
    def generate_dummy_image(self, resolution):
        """解像度に応じたダミー画像を生成"""
        resolutions = {
            "QVGA": (320, 240),
            "VGA": (640, 480),
            "SVGA": (800, 600),
            "XGA": (1024, 768),
            "UXGA": (1600, 1200)
        }
        
        width, height = resolutions.get(resolution, (640, 480))
        
        # カラフルなテストパターン生成
        img = Image.new('RGB', (width, height))
        pixels = img.load()
        
        for y in range(height):
            for x in range(width):
                r = int((x / width) * 255)
                g = int((y / height) * 255)
                b = 128
                pixels[x, y] = (r, g, b)
        
        # JPEG圧縮
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()
    
    def send_response(self, req_id, image_bytes, resolution):
        """画像レスポンスを送信"""
        # Base64エンコード
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        response = {
            "id": req_id,
            "image": image_b64,
            "width": Image.open(io.BytesIO(image_bytes)).width,
            "height": Image.open(io.BytesIO(image_bytes)).height,
            "size_bytes": len(image_bytes),
            "format": "jpeg"
        }
        
        response_topic = f"mcp/{self.device_id}/response/{req_id}"
        self.client.publish(response_topic, json.dumps(response))
        print(f"[RESPONSE] Sent to: {response_topic}")
        print(f"Image size: {len(image_bytes)} bytes, Base64: {len(image_b64)} chars")
    
    def publish_status(self):
        """ステータス送信"""
        status = {
            "device_id": self.device_id,
            "status": "online",
            "uptime_sec": int(time.time()),
            "free_heap": 123456,
            "wifi_rssi": -45
        }
        
        status_topic = f"office/camera/{self.device_id}/status"
        self.client.publish(status_topic, json.dumps(status))
        print(f"[STATUS] Published to: {status_topic}")
    
    def run(self):
        """メインループ"""
        print(f"=== Camera Node Simulator ===")
        print(f"Device ID: {self.device_id}")
        print(f"Broker: {self.broker}:{self.port}")
        
        self.client.connect(self.broker, self.port)
        self.client.loop_start()
        
        try:
            while True:
                time.sleep(30)
                self.publish_status()
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.client.loop_stop()
            self.client.disconnect()

if __name__ == "__main__":
    device_id = sys.argv[1] if len(sys.argv) > 1 else "camera_node_01"
    simulator = CameraNodeSimulator(device_id=device_id)
    simulator.run()
