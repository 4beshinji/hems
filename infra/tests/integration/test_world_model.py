#!/usr/bin/env python3
"""
Test script to verify World Model data flow.
Simulates various edge devices sending sensor data to test integration.
"""
import os
import paho.mqtt.client as mqtt
import json
import time
import random
from datetime import datetime

MQTT_USER = os.getenv("MQTT_USER", "soms")
MQTT_PASS = os.getenv("MQTT_PASS", "soms_dev_mqtt")


class MockEdgeDevice:
    """Simulates an edge device sending sensor data."""
    
    def __init__(self, mqtt_client, zone: str, device_type: str, device_id: str):
        self.client = mqtt_client
        self.zone = zone
        self.device_type = device_type
        self.device_id = device_id
    
    def get_topic(self, channel: str) -> str:
        """Generate MQTT topic."""
        return f"office/{self.zone}/{self.device_type}/{self.device_id}/{channel}"
    
    def publish(self, channel: str, data: dict):
        """Publish data to MQTT."""
        topic = self.get_topic(channel)
        payload = json.dumps(data)
        self.client.publish(topic, payload)
        print(f"📤 Published to {topic}: {data}")


class TemperatureSensor(MockEdgeDevice):
    """Temperature sensor simulation."""
    
    def __init__(self, mqtt_client, zone: str, device_id: str):
        super().__init__(mqtt_client, zone, "sensor", device_id)
        self.base_temp = 22.0  # Base temperature
    
    def send_reading(self):
        """Send temperature reading."""
        # Simulate slight variations
        temperature = self.base_temp + random.uniform(-1.5, 1.5)
        self.publish("temperature", {"value": round(temperature, 1)})


class CO2Sensor(MockEdgeDevice):
    """CO2 sensor simulation."""
    
    def __init__(self, mqtt_client, zone: str, device_id: str):
        super().__init__(mqtt_client, zone, "sensor", device_id)
        self.base_co2 = 600  # Base CO2 level
    
    def send_reading(self):
        """Send CO2 reading."""
        # Simulate increase when occupied
        co2 = self.base_co2 + random.randint(-50, 100)
        self.publish("co2", {"value": co2})
    
    def send_high_co2(self):
        """Simulate high CO2 (triggering ventilation alert)."""
        co2 = random.randint(1100, 1500)
        self.publish("co2", {"value": co2})
        print("⚠️  HIGH CO2 ALERT!")


class CameraSensor(MockEdgeDevice):
    """Camera/YOLO sensor simulation."""
    
    def __init__(self, mqtt_client, zone: str, device_id: str):
        super().__init__(mqtt_client, zone, "camera", device_id)
        self.person_count = 0
    
    def send_occupancy(self, count: int, activity_distribution: dict = None):
        """Send occupancy data."""
        self.person_count = count
        
        data = {
            "person_count": count
        }
        
        if activity_distribution:
            data["activity_distribution"] = activity_distribution
            data["avg_motion_level"] = random.uniform(0.2, 0.9)
        
        self.publish("activity", data)


class CoffeeMachine(MockEdgeDevice):
    """Coffee machine simulation."""
    
    def __init__(self, mqtt_client, zone: str, device_id: str):
        super().__init__(mqtt_client, zone, "coffee_machine", device_id)
    
    def send_status(self, beans_level: int):
        """Send coffee machine status."""
        self.publish("status", {
            "beans_level": beans_level,
            "water_level": random.randint(50, 100)
        })
        
        if beans_level == 0:
            print("☕ COFFEE BEANS EMPTY!")


def on_connect(client, userdata, flags, rc, properties=None):
    """MQTT connection callback."""
    if rc == 0:
        print("✅ Connected to MQTT broker")
    else:
        print(f"❌ Connection failed with code {rc}")


def main():
    """Main test sequence."""
    print("=" * 60)
    print("🧪 World Model Data Flow Test")
    print("=" * 60)
    
    # Connect to MQTT
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_edge_device")
    client.on_connect = on_connect
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    try:
        client.connect("localhost", 1883, 60)
        client.loop_start()
        time.sleep(1)  # Wait for connection
        
        # Create virtual devices for different zones
        print("\n📍 Setting up virtual devices...")
        
        # Meeting Room A devices
        temp_sensor_1 = TemperatureSensor(client, "meeting_room_a", "temp_01")
        co2_sensor_1 = CO2Sensor(client, "meeting_room_a", "co2_01")
        camera_1 = CameraSensor(client, "meeting_room_a", "cam_01")
        
        # Kitchen devices
        temp_sensor_2 = TemperatureSensor(client, "kitchen", "temp_02")
        coffee_machine = CoffeeMachine(client, "kitchen", "machine_01")
        
        # Library devices
        temp_sensor_3 = TemperatureSensor(client, "library", "temp_03")
        camera_2 = CameraSensor(client, "library", "cam_02")
        
        print("\n" + "=" * 60)
        print("🔄 Test Sequence Start")
        print("=" * 60)
        
        # Test 1: Initial state (empty office)
        print("\n[Test 1] Initial state - Empty office")
        time.sleep(1)
        
        temp_sensor_1.send_reading()
        temp_sensor_2.send_reading()
        temp_sensor_3.send_reading()
        camera_1.send_occupancy(0)
        camera_2.send_occupancy(0)
        coffee_machine.send_status(beans_level=50)
        
        time.sleep(3)
        
        # Test 2: People arrive in meeting room (active state)
        print("\n[Test 2] People arrive - Meeting room active")
        time.sleep(1)
        
        camera_1.send_occupancy(5, {
            "active": 4,
            "focused": 1
        })
        temp_sensor_1.base_temp = 24.0  # Temperature rises
        temp_sensor_1.send_reading()
        co2_sensor_1.send_reading()
        
        time.sleep(3)
        
        # Test 3: Library occupied (focused state)
        print("\n[Test 3] Library occupied - Focused work")
        time.sleep(1)
        
        camera_2.send_occupancy(3, {
            "active": 0,
            "focused": 3
        })
        temp_sensor_3.send_reading()
        
        time.sleep(3)
        
        # Test 4: CO2 spike in meeting room
        print("\n[Test 4] CO2 threshold exceeded")
        time.sleep(1)
        
        co2_sensor_1.send_high_co2()
        
        time.sleep(3)
        
        # Test 5: Coffee beans empty
        print("\n[Test 5] Coffee beans depleted")
        time.sleep(1)
        
        coffee_machine.send_status(beans_level=0)
        
        time.sleep(3)
        
        # Test 6: Multiple sensors in same zone (sensor fusion test)
        print("\n[Test 6] Sensor fusion - Multiple temperature sensors")
        time.sleep(1)
        
        # Simulate multiple temp sensors in meeting room
        temp_sensor_1a = TemperatureSensor(client, "meeting_room_a", "temp_01a")
        temp_sensor_1b = TemperatureSensor(client, "meeting_room_a", "temp_01b")
        
        temp_sensor_1a.base_temp = 23.5
        temp_sensor_1b.base_temp = 24.5
        
        temp_sensor_1a.send_reading()
        temp_sensor_1b.send_reading()
        
        time.sleep(3)
        
        # Test 7: Zone evacuation
        print("\n[Test 7] Zone evacuation - People leave")
        time.sleep(1)
        
        camera_1.send_occupancy(0)
        camera_2.send_occupancy(0)
        
        time.sleep(3)
        
        print("\n" + "=" * 60)
        print("✅ Test sequence completed!")
        print("=" * 60)
        print("\nℹ️  Next steps:")
        print("1. Check Brain service logs: docker logs -f soms-brain")
        print("2. Verify World Model state in Brain")
        print("3. Check Dashboard API: curl http://localhost:8000/tasks")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.loop_stop()
        client.disconnect()
        print("\n🔌 Disconnected from MQTT broker")


if __name__ == "__main__":
    main()
