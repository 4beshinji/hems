"""Domain-specific RuleEngine rules.

Extracted as a mixin to keep RuleEngine public methods stable.
"""


class ShoppingRulesMixin:
    def _evaluate_shopping_rules(self, wm, now: float) -> list[dict]:
        """Shopping list rules: recurring due reminders + departure notification."""
        actions = []
        shopping = wm.shopping_state

        # Recurring items due for purchase (24h cooldown per item)
        for item in shopping.due_items:
            key = f"shopping_due_{item.name}"
            if self._check_cooldown_daily(key, now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"「{item.name}」がそろそろ必要です。買い物リストを確認してください。",
                            "zone": "living_room",
                            "tone": "caring",
                        },
                    }
                )

        # Departure notification: occupancy drops to 0 with pending items.
        # Reconciled presence (camera + PIR + motion + PC + HR) prevents a
        # momentary camera dropout from nagging the user about shopping.
        if shopping.pending_count > 0:
            has_recent_zones = any(z.occupancy.last_update > now - 300 for z in wm.zones.values() if z.occupancy)
            all_empty = has_recent_zones and not wm.is_anyone_home()
            if all_empty and has_recent_zones:
                if self._check_cooldown("shopping_departure", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"外出検知。買い物リストに{shopping.pending_count}件のアイテムがあります。",
                                "zone": "living_room",
                                "tone": "caring",
                            },
                        }
                    )

        return actions
