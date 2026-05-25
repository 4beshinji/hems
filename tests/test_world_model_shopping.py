"""
Tests for the ShoppingState reducer (hems/shopping/list snapshot).

ShoppingState was previously a dead dataclass with no reducer; the backend now
publishes a full pending-list snapshot that the world model rebuilds into
ShoppingState, making the recurring-due / departure reminder rules live.
"""

import time


def _snapshot(items):
    return {"items": items, "count": len(items), "timestamp": time.time()}


class TestShoppingStateReducer:
    def test_list_snapshot_populates_items(self, world_model):
        world_model.update_from_mqtt(
            "hems/shopping/list",
            _snapshot([{"id": 1, "name": "coffee", "quantity": 2}]),
        )
        assert world_model.shopping_state.pending_count == 1
        assert world_model.shopping_state.items[0].name == "coffee"
        assert world_model.shopping_state.items[0].quantity == 2

    def test_snapshot_replaces_previous_state(self, world_model):
        world_model.update_from_mqtt("hems/shopping/list", _snapshot([{"id": 1, "name": "coffee"}]))
        world_model.update_from_mqtt("hems/shopping/list", _snapshot([{"id": 2, "name": "rice"}]))
        assert world_model.shopping_state.pending_count == 1
        assert world_model.shopping_state.items[0].name == "rice"

    def test_empty_snapshot_clears_items(self, world_model):
        world_model.update_from_mqtt("hems/shopping/list", _snapshot([{"id": 1, "name": "coffee"}]))
        world_model.update_from_mqtt("hems/shopping/list", _snapshot([]))
        assert world_model.shopping_state.pending_count == 0

    def test_due_items_reflects_recurring_past_due(self, world_model):
        now = time.time()
        world_model.update_from_mqtt(
            "hems/shopping/list",
            _snapshot(
                [
                    {"id": 1, "name": "milk", "is_recurring": True, "next_purchase_at": now - 100},
                    {"id": 2, "name": "eggs", "is_recurring": True, "next_purchase_at": now + 10000},
                    {"id": 3, "name": "snack", "is_recurring": False, "next_purchase_at": 0},
                ]
            ),
        )
        due_names = [i.name for i in world_model.shopping_state.due_items]
        assert due_names == ["milk"]

    def test_malformed_items_skipped(self, world_model):
        world_model.update_from_mqtt(
            "hems/shopping/list",
            _snapshot(["not-a-dict", {"id": 5, "name": "tea"}]),
        )
        assert world_model.shopping_state.pending_count == 1
        assert world_model.shopping_state.items[0].name == "tea"
