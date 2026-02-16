"""
Dispatch decision logic — simplified for single-user home.
"""


def should_dispatch(task: dict, world_model) -> bool:
    """Decide if a queued task should be dispatched now."""
    zone = task.get("zone", "")

    # Always dispatch critical tasks
    if task.get("urgency", 0) >= 4:
        return True

    # Check if someone is home (any zone has occupancy)
    someone_home = any(
        z.occupancy and z.occupancy.count > 0
        for z in world_model.zones.values()
    )

    if not someone_home:
        return False  # Don't dispatch if nobody is home

    return True
