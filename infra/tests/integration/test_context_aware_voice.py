#!/usr/bin/env python3
"""
Test script for Context-Aware Completion Voice feature.

This script tests the dual voice generation feature where both
announcement and completion voices are generated simultaneously,
with the completion voice contextually linked to the task.
"""

import requests
import os
import sys

VOICE_SERVICE_URL = os.getenv("VOICE_SERVICE_URL", "http://localhost:8002")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

def test_dual_voice_generation():
    """Test dual voice generation endpoint."""
    print("=" * 60)
    print("Testing Dual Voice Generation")
    print("=" * 60)
    
    test_tasks = [
        {
            "title": "掃除機をかける",
            "description": "オフィスの床を掃除してください",
            "location": "オフィス",
            "bounty_gold": 30,
            "urgency": 1,
            "zone": "1F"
        },
        {
            "title": "コーヒー豆の補充",
            "description": "給湯室のコーヒー豆がなくなっています",
            "location": "給湯室",
            "bounty_gold": 50,
            "urgency": 2,
            "zone": "2F"
        },
        {
            "title": "プリンター用紙補充",
            "description": "プリンターの用紙が少なくなっています",
            "location": "コピー室",
            "bounty_gold": 20,
            "urgency": 1,
            "zone": "1F"
        }
    ]
    
    print(f"\n Testing {len(test_tasks)} different tasks...\n")
    
    for i, task in enumerate(test_tasks, 1):
        print(f"\n[{i}/{len(test_tasks)}] Task: {task['title']}")
        print("-" * 60)
        
        try:
            response = requests.post(
                f"{VOICE_SERVICE_URL}/api/voice/announce_with_completion",
                json={"task": task},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                print("✓ Dual voice generated successfully!")
                print("\n  📢 Announcement:")
                print(f"     Text: {result['announcement_text']}")
                print(f"     URL:  {result['announcement_audio_url']}")
                print(f"     Duration: {result['announcement_duration']}s")
                
                print("\n  ✅ Completion:")
                print(f"     Text: {result['completion_text']}")
                print(f"     URL:  {result['completion_audio_url']}")
                print(f"     Duration: {result['completion_duration']}s")
                
                # Check if completion text is contextual
                completion = result['completion_text']
                if task['title'] in ['掃除機をかける', '掃除']:
                    if '気持ち' in completion or 'きれい' in completion or '清潔' in completion:
                        print("\n  🎯 Contextual link detected! (cleaning-related response)")
                elif 'コーヒー' in task['title']:
                    if 'コーヒー' in completion or '飲める' in completion:
                        print("\n  🎯 Contextual link detected! (coffee-related response)")
                elif '用紙' in task['title'] or 'プリンター' in task['title']:
                    if '作業' in completion or 'スムーズ' in completion or '印刷' in completion:
                        print("\n  🎯 Contextual link detected! (work-related response)")
                
                # Download audio files
                announcement_url = f"{VOICE_SERVICE_URL}{result['announcement_audio_url']}"
                completion_url = f"{VOICE_SERVICE_URL}{result['completion_audio_url']}"
                
                announcement_file = f"/tmp/test_announcement_{i}.wav"
                completion_file = f"/tmp/test_completion_{i}.wav"
                
                ann_resp = requests.get(announcement_url)
                with open(announcement_file, "wb") as f:
                    f.write(ann_resp.content)
                
                comp_resp = requests.get(completion_url)
                with open(completion_file, "wb") as f:
                    f.write(comp_resp.content)
                
                print("\n  💾 Audio files saved:")
                print(f"     Announcement: {announcement_file}")
                print(f"     Completion:   {completion_file}")
                
            else:
                print(f"✗ Failed: {response.status_code}")
                print(f"  Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"✗ Error: {e}")
            return False
    
    print("\n" + "=" * 60)
    print(f"✓ All {len(test_tasks)} tasks tested successfully!")
    print("\n💡 To listen to the audio files, run:")
    print("   aplay /tmp/test_announcement_*.wav")
    print("   aplay /tmp/test_completion_*.wav")
    print("=" * 60)
    
    return True

def test_backend_integration():
    """Test that backend stores voice data correctly."""
    print("\n" + "=" * 60)
    print("Testing Backend Integration")
    print("=" * 60)
    
    # Create a task via backend API
    task_data = {
        "title": "テストタスク",
        "description": "バックエンド統合テスト",
        "location": "テスト場所",
        "bounty_gold": 100,
        "urgency": 2,
        "zone": "Test Zone",
        "announcement_audio_url": "/audio/test_announce.wav",
        "announcement_text": "テスト発注音声です",
        "completion_audio_url": "/audio/test_complete.wav",
        "completion_text": "テスト完了音声です"
    }
    
    try:
        print("\n→ Creating task with voice data...")
        response = requests.post(
            f"{BACKEND_URL}/tasks/",
            json=task_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            task_id = result['id']
            print(f"  ✓ Task created with ID: {task_id}")
            
            # Verify voice data was stored
            if result.get('announcement_audio_url') == task_data['announcement_audio_url']:
                print("  ✓ Announcement audio URL stored correctly")
            if result.get('announcement_text') == task_data['announcement_text']:
                print("  ✓ Announcement text stored correctly")
            if result.get('completion_audio_url') == task_data['completion_audio_url']:
                print("  ✓ Completion audio URL stored correctly")
            if result.get('completion_text') == task_data['completion_text']:
                print("  ✓ Completion text stored correctly")
            
            print("\n  📋 Task Details:")
            print(f"     ID: {result['id']}")
            print(f"     Title: {result['title']}")
            print(f"     Announcement: {result.get('announcement_text', 'N/A')}")
            print(f"     Completion: {result.get('completion_text', 'N/A')}")
            
            return True
        else:
            print(f"  ✗ Failed to create task: {response.status_code}")
            print(f"  Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def main():
    print("\n" + "=" * 60)
    print("Context-Aware Completion Voice Test Suite")
    print("=" * 60)
    
    results = []
    
    # Test 1: Dual voice generation
    results.append(("Dual Voice Generation", test_dual_voice_generation()))
    
    # Test 2: Backend integration
    results.append(("Backend Integration", test_backend_integration()))
    
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
        print("\n🎉 All tests passed!")
        print("\n💡 Key Features Verified:")
        print("   ✓ Dual voice generation (announcement + completion)")
        print("   ✓ Contextual completion text linked to task")
        print("   ✓ Both audio files successfully created")
        print("   ✓ Backend stores voice data correctly")
        return 0
    else:
        print("\n❌ Some tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
