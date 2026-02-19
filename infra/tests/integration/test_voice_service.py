#!/usr/bin/env python3
"""
Test script for VOICEVOX Voice Service integration.

This script verifies:
1. VOICEVOX engine is running
2. Voice service can generate speech
3. LLM integration works
4. Audio files are created
5. End-to-end task announcement flow
"""

import requests
import time
import os
import sys

VOICE_SERVICE_URL = os.getenv("VOICE_SERVICE_URL", "http://localhost:8002")
VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://localhost:50021")

def test_voicevox_engine():
    """Test if VOICEVOX engine is accessible."""
    print("1. Testing VOICEVOX Engine...")
    try:
        response = requests.get(f"{VOICEVOX_URL}/version", timeout=5)
        if response.status_code == 200:
            version = response.json()
            print(f"   ✓ VOICEVOX Engine is running (version: {version})")
            return True
        else:
            print(f"   ✗ VOICEVOX Engine returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ VOICEVOX Engine is not accessible: {e}")
        return False

def test_voice_service_health():
    """Test if voice service is accessible."""
    print("\n2. Testing Voice Service Health...")
    try:
        response = requests.get(f"{VOICE_SERVICE_URL}/", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Voice Service is running: {data.get('service')}")
            return True
        else:
            print(f"   ✗ Voice Service returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ Voice Service is not accessible: {e}")
        return False

def test_task_announcement():
    """Test task announcement with voice."""
    print("\n3. Testing Task Announcement...")
    
    task_data = {
        "task": {
            "title": "コーヒー豆の補充",
            "description": "給湯室のコーヒー豆がなくなっています",
            "location": "給湯室",
            "bounty_gold": 50,
            "urgency": 2,
            "zone": "2F"
        }
    }
    
    try:
        print("   → Sending task announcement request...")
        response = requests.post(
            f"{VOICE_SERVICE_URL}/api/voice/announce",
            json=task_data,
            timeout=30  # LLM + VOICEVOX can take time
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✓ Task announced successfully!")
            print(f"   → Generated text: {result.get('text_generated')}")
            print(f"   → Audio URL: {result.get('audio_url')}")
            print(f"   → Duration: {result.get('duration_seconds')}s")
            
            # Try to download audio
            audio_url = f"{VOICE_SERVICE_URL}{result.get('audio_url')}"
            print(f"\n   → Downloading audio from {audio_url}...")
            audio_response = requests.get(audio_url, timeout=10)
            
            if audio_response.status_code == 200:
                output_file = "/tmp/test_task_announcement.wav"
                with open(output_file, "wb") as f:
                    f.write(audio_response.content)
                print(f"   ✓ Audio saved to {output_file}")
                print(f"   → File size: {len(audio_response.content)} bytes")
                
                # Suggest playback command
                print(f"\n   💡 To listen to the audio, run:")
                print(f"      aplay {output_file}")
                print(f"      # or")
                print(f"      mpv {output_file}")
                
                return True
            else:
                print(f"   ✗ Failed to download audio: {audio_response.status_code}")
                return False
        else:
            print(f"   ✗ Task announcement failed: {response.status_code}")
            print(f"   → Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ✗ Task announcement error: {e}")
        return False

def test_feedback_generation():
    """Test feedback message generation."""
    print("\n4. Testing Feedback Generation...")
    
    feedback_types = ["task_completed", "task_accepted"]
    
    for feedback_type in feedback_types:
        print(f"\n   → Testing '{feedback_type}' feedback...")
        try:
            response = requests.post(
                f"{VOICE_SERVICE_URL}/api/voice/feedback/{feedback_type}",
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✓ Feedback generated!")
                print(f"   → Text: {result.get('text_generated')}")
                print(f"   → Duration: {result.get('duration_seconds')}s")
            else:
                print(f"   ✗ Feedback generation failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ✗ Feedback generation error: {e}")
            return False
    
    return True

def test_variety():
    """Test that multiple calls generate different text (no caching)."""
    print("\n5. Testing Speech Variety...")
    
    task_data = {
        "task": {
            "title": "掃除機をかける",
            "description": "オフィスの床を掃除してください",
            "location": "オフィス",
            "bounty_gold": 30,
            "urgency": 1,
            "zone": "1F"
        }
    }
    
    generated_texts = []
    
    for i in range(3):
        print(f"\n   → Attempt {i+1}/3...")
        try:
            response = requests.post(
                f"{VOICE_SERVICE_URL}/api/voice/announce",
                json=task_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                text = result.get('text_generated')
                generated_texts.append(text)
                print(f"   → Generated: {text}")
            else:
                print(f"   ✗ Request failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False
    
    # Check if we got variety
    unique_texts = set(generated_texts)
    if len(unique_texts) > 1:
        print(f"\n   ✓ Variety confirmed! {len(unique_texts)}/3 unique texts generated")
        print("   → This shows LLM is generating varied responses (no caching)")
        return True
    else:
        print(f"\n   ⚠ All texts were identical")
        print("   → LLM might be using low temperature or caching is enabled")
        return False

def main():
    print("=" * 60)
    print("VOICEVOX Voice Service Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("VOICEVOX Engine", test_voicevox_engine()))
    results.append(("Voice Service Health", test_voice_service_health()))
    results.append(("Task Announcement", test_task_announcement()))
    results.append(("Feedback Generation", test_feedback_generation()))
    results.append(("Speech Variety", test_variety()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Voice service is fully functional.")
        print("\n💡 Next steps:")
        print("   1. Create a task via Brain service")
        print("   2. Listen for voice announcement")
        print("   3. Verify ナースロボ＿タイプＴ voice quality")
        return 0
    else:
        print("\n❌ Some tests failed. Please check the logs above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
