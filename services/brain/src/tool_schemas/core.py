"""Grouped OpenAI tool schemas."""


def _get_service_tools() -> list:
    """Service monitor tools — only included when services are being tracked."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_service_status",
                "description": "外部サービスの状態を取得する（Gmail未読数、GitHub通知など）。サービス名を省略すると全サービスを返す。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_name": {
                            "type": "string",
                            "description": "サービス名（例: gmail, github）。省略で全サービス取得",
                        },
                    },
                },
            },
        },
    ]


def _get_system_tools() -> list:
    """System control tools — always available."""
    return [
        {
            "type": "function",
            "function": {
                "name": "set_guest_mode",
                "description": "ゲストモードのON/OFF。来客時に自動化を一時停止する。ONで個人的な通知・生体ルールを抑制。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean", "description": "ON/OFF"},
                        "duration_hours": {"type": "number", "description": "自動解除までの時間（デフォルト4時間）"},
                    },
                    "required": ["enabled"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "現在の天気と予報を取得する。天気連動の判断に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]


def _get_shopping_tools() -> list:
    """Shopping list tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "add_shopping_item",
                "description": "買い物リストにアイテムを追加する。「牛乳切れた」などの発言から自動追加する場合にも使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "アイテム名（例: 牛乳, 洗剤）"},
                        "category": {
                            "type": "string",
                            "description": "カテゴリ（食品, 日用品, 消耗品, 飲料, 調味料, 文具）",
                        },
                        "quantity": {"type": "integer", "description": "数量", "default": 1},
                        "unit": {"type": "string", "description": "単位（個, 本, パック, 袋）"},
                        "store": {"type": "string", "description": "購入する店舗名"},
                        "price": {"type": "integer", "description": "想定価格（円）"},
                        "is_recurring": {"type": "boolean", "description": "定期購入フラグ", "default": False},
                        "recurrence_days": {"type": "integer", "description": "定期購入の間隔（日数）"},
                        "priority": {
                            "type": "integer",
                            "description": "優先度 0=低, 1=通常, 2=高",
                            "minimum": 0,
                            "maximum": 2,
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_shopping_list",
                "description": "現在の買い物リストを取得する。外出検知時の通知や在庫確認に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "description": "カテゴリでフィルタ"},
                        "store": {"type": "string", "description": "店舗でフィルタ"},
                    },
                },
            },
        },
    ]
