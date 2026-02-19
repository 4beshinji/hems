import asyncio
import os
import sys

# Add the src directory to path so we can import dashboard_client
sys.path.append(os.path.join(os.getcwd(), "services/brain/src"))

from dashboard_client import DashboardClient

async def main():
    # Initialize client
    # Since we are running outside of docker, we point to localhost
    client = DashboardClient(
        api_url="http://localhost:8000",
        voice_url="http://localhost:8002"
    )
    
    print("Creating a dummy task...")
    task = await client.create_task(
        title="午後のティータイムの準備",
        description="リフレッシュの時間です！ラウンジに紅茶とお菓子を用意してみんなを驚かせましょう。",
        bounty=500,
        task_types=["general"],
        urgency=1,
        zone="Lounge",
        announce=True
    )
    
    if task:
        print(f"Successfully created task: {task['title']} (ID: {task['id']})")
        print(f"Announcement Audio: {task.get('announcement_audio_url')}")
    else:
        print("Failed to create task.")

if __name__ == "__main__":
    asyncio.run(main())
