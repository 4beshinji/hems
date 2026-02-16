"""
OpenAI function-calling tool definitions for HEMS Brain.
4 tools: create_task, send_device_command, get_zone_status, speak
"""


def get_tools() -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": "create_task",
                "description": "ダッシュボードに人間向けタスクを作成する。継続的な問題や人間のアクションが必要な場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "タスクのタイトル（日本語、簡潔に）"},
                        "description": {"type": "string", "description": "タスクの詳細説明"},
                        "xp_reward": {"type": "integer", "description": "XP報酬 (50-500)", "minimum": 50, "maximum": 500},
                        "urgency": {"type": "integer", "description": "緊急度 0=延期可 1=低 2=通常 3=高 4=緊急", "minimum": 0, "maximum": 4},
                        "zone": {"type": "string", "description": "ゾーン名 (例: living_room, bedroom)"},
                        "task_type": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "タスク種別タグ (例: ['ventilation'], ['cleaning'])"
                        },
                        "location": {"type": "string", "description": "具体的な場所"},
                        "estimated_duration": {"type": "integer", "description": "推定所要時間（分）", "default": 10},
                    },
                    "required": ["title", "description", "xp_reward", "urgency", "zone"],
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
                        "message": {"type": "string", "description": "メッセージ（70文字以内、日本語）", "maxLength": 70},
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
    ]
