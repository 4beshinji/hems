
import requests
import time
import sys
from datetime import datetime, timedelta, timezone

def check():
    # 1. Create Task A
    print("Creating Task A...")
    try:
        r = requests.post("http://localhost:8000/tasks/", json={
            "title": "Task A",
            "description": "Desc A",
            "bounty_gold": 100,
            "task_type": ["general", "clean"],
            "expires_at": None,
            "location": "Office"
        })
        if r.status_code != 200:
            print(f"Failed to create Task A: {r.status_code} {r.text}")
            return False
        t1 = r.json()
        print(f"Task A created: ID={t1['id']} Types={t1.get('task_type')}")
        if t1.get('task_type') != ["general", "clean"]:
             print(f"ERROR: Task type mismatch: {t1.get('task_type')}")
             return False
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

    # 2. Duplicate Check
    print("Creating Task A again (Duplicate)...")
    r = requests.post("http://localhost:8000/tasks/", json={
        "title": "Task A",
        "description": "Desc A Duplicate",
        "bounty_gold": 200,
        "task_type": ["urgent"],
        "expires_at": None,
        "location": "Office"
    })
    if r.status_code != 200:
        print(f"Failed to create Duplicate Task A: {r.status_code} {r.text}")
        return False
    t2 = r.json()
    print(f"Task A Duplicate created: ID={t2['id']}")

    # Check count
    r = requests.get("http://localhost:8000/tasks/")
    tasks = r.json()
    print(f"Total tasks: {len(tasks)}")
    
    current_ids = [t['id'] for t in tasks]
    if t1['id'] in current_ids and t1['id'] != t2['id']:
        print("ERROR: Old task was NOT deleted!")
        return False
    
    # 3. Expiration Check
    print("Creating Expiring Task B...")
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    
    r = requests.post("http://localhost:8000/tasks/", json={
        "title": "Task B",
        "description": "Expiring",
        "bounty_gold": 50,
        "task_type": ["short"],
        "expires_at": expires_at,
        "location": "Office"
    })
    if r.status_code != 200:
        print(f"Failed to create Task B: {r.status_code} {r.text}")
        return False
    t3 = r.json()
    print(f"Task B created: ID={t3['id']}")

    print("Waiting 4 seconds for expiration...")
    time.sleep(4)

    r = requests.get("http://localhost:8000/tasks/")
    tasks = r.json()
    print(f"Total tasks after wait: {len(tasks)}")
    
    ids = [t['id'] for t in tasks]
    if t3['id'] in ids:
        print("ERROR: Task B should be expired and hidden!")
        return False
    
    print("SUCCESS: Smart Task Management Verified.")
    return True

if __name__ == "__main__":
    if not check():
        sys.exit(1)
