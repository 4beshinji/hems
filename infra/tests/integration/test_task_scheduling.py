#!/usr/bin/env python3
"""
Test script to verify Intelligent Task Scheduling.
Tests task queue management, dispatch decisions, and priority handling.
"""
import asyncio
import aiohttp
import time
from datetime import datetime, timedelta, timezone


BASE_URL = "http://localhost:8000"


async def create_task(title: str, description: str, urgency: int, zone: str = None, min_people: int = 1):
    """Create a task via Dashboard API."""
    url = f"{BASE_URL}/tasks/"
    
    # Calculate expires_at (24 hours from now)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    
    payload = {
        "title": title,
        "description": description,
        "bounty_gold": 100 * (urgency + 1),
        "task_type": ["test"],
        "location": zone or "Office",
        "urgency": urgency,
        "zone": zone,
        "min_people_required": min_people,
        "estimated_duration": 10,
        "expires_at": expires_at
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                data = await response.json()
                print(f"✅ Task created: '{title}' (ID: {data['id']}, Urgency: {urgency}, Queued: {data.get('is_queued', False)})")
                return data
            else:
                text = await response.text()
                print(f"❌ Failed to create task: {response.status} - {text}")
                return None


async def get_tasks():
    """Get all tasks."""
    url = f"{BASE_URL}/tasks/"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return []


async def get_queue():
    """Get queued tasks."""
    url = f"{BASE_URL}/tasks/queue"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return []


async def get_stats():
    """Get task statistics."""
    url = f"{BASE_URL}/tasks/stats"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return {}


async def main():
    """Main test sequence."""
    print("=" * 70)
    print("🧪 Intelligent Task Scheduling Test")
    print("=" * 70)
    
    # Test 1: Critical task (should dispatch immediately)
    print("\n[Test 1] Critical task (urgency=4) - Should dispatch immediately")
    await create_task(
        title="Safety Alert: Fire Alarm Test",
        description="Immediate action required",
        urgency=4,
        zone="meeting_room_a"
    )
    
    await asyncio.sleep(2)
    
    # Test 2: High urgency task
    print("\n[Test 2] High urgency task (urgency=3)")
    await create_task(
        title="Fix Broken Printer",
        description="Printer in library is jammed",
        urgency=3,
        zone="library"
    )
    
    await asyncio.sleep(2)
    
    # Test 3: Normal task requiring specific zone
    print("\n[Test 3] Normal task (urgency=2) requiring zone with people")
    await create_task(
        title="Collect Whiteboard Markers",
        description="Please collect markers from meeting room",
        urgency=2,
        zone="meeting_room_a",
        min_people=1
    )
    
    await asyncio.sleep(2)
    
    # Test 4: Low urgency task
    print("\n[Test 4] Low urgency task (urgency=1)")
    await create_task(
        title="Water Office Plants",
        description="Plants in the office need watering",
        urgency=1,
        zone="office"
    )
    
    await asyncio.sleep(2)
    
    # Test 5: Deferred task
    print("\n[Test 5] Deferred task (urgency=0)")
    await create_task(
        title="Organize Supply Closet",
        description="Can be done anytime",
        urgency=0,
        zone="storage"
    )
    
    await asyncio.sleep(2)
    
    # Test 6: Task requiring multiple people
    print("\n[Test 6] Task requiring 2+ people")
    await create_task(
        title="Move Heavy Equipment",
        description="Requires 2 people",
        urgency=2,
        zone="workshop",
        min_people=2
    )
    
    await asyncio.sleep(3)
    
    # Check results
    print("\n" + "=" * 70)
    print("📊 Test Results")
    print("=" * 70)
    
    print("\n[All Tasks]")
    tasks = await get_tasks()
    for task in tasks[-6:]:  # Last 6 tasks
        status = "🟢 Dispatched" if not task.get('is_queued', False) else "🟡 Queued"
        print(f"  {status} - {task['title']} (Urgency: {task.get('urgency', 2)})")
    
    print("\n[Queued Tasks]")
    queued = await get_queue()
    if queued:
        for task in queued:
            print(f"  ⏸️  {task['title']} (Urgency: {task.get('urgency', 2)}, Zone: {task.get('zone', 'N/A')})")
    else:
        print("  (No queued tasks - all dispatched immediately)")
    
    print("\n[Statistics]")
    stats = await get_stats()
    print(f"  Active tasks: {stats.get('tasks_active', 0)}")
    print(f"  Queued tasks: {stats.get('tasks_queued', 0)}")
    print(f"  Completed (last hour): {stats.get('tasks_completed_last_hour', 0)}")
    
    print("\n" + "=" * 70)
    print("✅ Test sequence completed!")
    print("=" * 70)
    print("\nℹ️  Observations:")
    print("1. Critical tasks (urgency=4) should always dispatch immediately")
    print("2. High urgency tasks (urgency=3) likely dispatch immediately")
    print("3. Normal/Low tasks may queue based on zone occupancy")
    print("4. Tasks requiring multiple people may queue until conditions are met")
    print("\nℹ️  Check Brain logs for dispatch decisions:")
    print("   docker logs -f soms-brain | grep -E 'Dispatching|Queuing|Task Queue'")


if __name__ == "__main__":
    asyncio.run(main())
