"""Base tool schemas always available to the Brain."""


def get_base_tools() -> list:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "create_task",
                "description": "ダッシュボードに人間向けタスクを作成する。継続的な問題や人間のアクションが必要な場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "タスクのタイトル（日本語、簡潔に）"},
                        "description": {"type": "string", "description": "タスクの詳細説明（状況と対応方法を含む）"},
                        "urgency": {
                            "type": "integer",
                            "description": "緊急度 0=延期可 1=低 2=通常 3=高 4=緊急",
                            "minimum": 0,
                            "maximum": 4,
                        },
                        "zone": {"type": "string", "description": "ゾーン名 (例: living_room, bedroom)"},
                        "task_type": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "タスク種別タグ (例: ['ventilation'], ['cleaning'])",
                        },
                        "location": {"type": "string", "description": "具体的な場所"},
                        "estimated_duration": {"type": "integer", "description": "推定所要時間（分）", "default": 10},
                    },
                    "required": ["title", "description", "urgency", "zone"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "send_device_command",
                "description": "MCP対応デバイスにコマンドを送信する。照明、エアコン、換気扇などの制御に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "デバイスのMCPエージェントID"},
                        "tool_name": {"type": "string", "description": "デバイスのツール名 (例: set_relay, set_led)"},
                        "arguments": {"type": "object", "description": "ツール引数 (JSON)"},
                    },
                    "required": ["agent_id", "tool_name", "arguments"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_zone_status",
                "description": "指定ゾーンの詳細な環境状態を取得する。判断に追加情報が必要な場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zone_id": {"type": "string", "description": "ゾーンID (例: living_room)"},
                    },
                    "required": ["zone_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "speak",
                "description": "音声で短いメッセージを通知する。一時的な注意喚起やアドバイスに使用。ダッシュボードには残らない。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "メッセージ（70文字以内、日本語）",
                            "maxLength": 70,
                        },
                        "zone": {"type": "string", "description": "対象ゾーン"},
                        "tone": {
                            "type": "string",
                            "enum": ["neutral", "caring", "humorous", "alert"],
                            "description": "声のトーン",
                            "default": "neutral",
                        },
                    },
                    "required": ["message", "zone"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_active_tasks",
                "description": "現在アクティブなタスク一覧を取得する。重複タスク作成を防止するために、タスク作成前に確認すること。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_device_status",
                "description": "デバイスネットワークの状態を取得する。オフライン、低バッテリー、通信エラーなどの問題を確認できる。デバイスコマンド送信前に状態確認として使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zone_id": {
                            "type": "string",
                            "description": "ゾーンID（省略時: 全ゾーン）",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_sensor_history",
                "description": (
                    "指定ゾーン・チャンネルのセンサー値履歴を返す (read-only)。"
                    "「さっきまでVOCが高かったか」等、最近の推移を確認するのに使う。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zone": {"type": "string", "description": "ゾーンID"},
                        "channel": {
                            "type": "string",
                            "description": "temperature/humidity/co2/pressure/voc/pm25/light/soil_moisture 等",
                        },
                        "hours": {
                            "type": "integer",
                            "description": "さかのぼる時間（1〜168）",
                            "minimum": 1,
                            "maximum": 168,
                            "default": 6,
                        },
                        "max_points": {
                            "type": "integer",
                            "description": "返す最大サンプル数",
                            "minimum": 1,
                            "maximum": 500,
                            "default": 200,
                        },
                    },
                    "required": ["zone", "channel"],
                },
            },
        },
    ]
    return tools
