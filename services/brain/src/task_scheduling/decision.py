"""
Dispatch decision logic — simplified for single-user home.
"""


def should_dispatch(task: dict, world_model) -> bool:
    """Decide if a queued task should be dispatched now."""
    # Always dispatch critical tasks
    if task.get("urgency", 0) >= 4:
        return True

    # Check if someone is home via multi-source presence inference, so a task
    # is not withheld when the camera is offline but PC/HR/PIR signal occupancy.
    if not world_model.is_anyone_home():
        return False  # Don't dispatch if nobody is home

    return True
