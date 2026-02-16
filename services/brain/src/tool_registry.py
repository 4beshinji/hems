"""
Tool Registry: OpenAI-compatible function definitions for LLM tool calling.
"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "ダッシュボードに人間向けタスクを作成する。オフィスの問題を検知した場合に使用。報酬（bounty）はタスクの難易度に応じて設定する。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "タスクのタイトル（日本語、簡潔に）"
                    },
                    "description": {
                        "type": "string",
                        "description": "タスクの詳細説明（状況と対応方法を含む）"
                    },
                    "bounty": {
                        "type": "integer",
                        "description": "報酬ポイント。簡単:500-1000、中程度:1000-2000、重労働:2000-5000"
                    },
                    "urgency": {
                        "type": "integer",
                        "description": "緊急度 0-4。0:後回し可、1:低、2:通常、3:高、4:緊急"
                    },
                    "zone": {
                        "type": "string",
                        "description": "タスクの対象ゾーン（例: main, kitchen）"
                    },
                    "task_types": {
                        "type": "string",
                        "description": "タスク種別をカンマ区切りで（例: environment,urgent）"
                    }
                },
                "required": ["title", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_device_command",
            "description": "MCPBridge経由でエッジデバイスにコマンドを送信する。エアコン操作、照明制御、窓の開閉などに使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "デバイスエージェントのID（例: edge_01）"
                    },
                    "tool_name": {
                        "type": "string",
                        "description": "実行するツール名（例: set_temperature, toggle_light）"
                    },
                    "arguments": {
                        "type": "string",
                        "description": "ツール引数をJSON文字列で指定（例: {\"temperature\": 24}）"
                    }
                },
                "required": ["agent_id", "tool_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_zone_status",
            "description": "WorldModelから指定ゾーンの詳細な状態を取得する。判断に追加情報が必要な場合に使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_id": {
                        "type": "string",
                        "description": "ゾーンID（例: main, kitchen, meeting_room_a）"
                    }
                },
                "required": ["zone_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "speak",
            "description": "音声でオフィスの人に直接話しかける。タスク発行が不要な場面（健康アドバイス、軽い注意、観察報告など）で使用。ダッシュボードには表示されない。",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "読み上げるメッセージ。自然な話し言葉で、70文字以内。"
                    },
                    "zone": {
                        "type": "string",
                        "description": "対象ゾーン"
                    },
                    "tone": {
                        "type": "string",
                        "description": "トーン: neutral(通常), caring(優しく), humorous(ユーモア), alert(注意喚起)"
                    }
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_tasks",
            "description": "現在アクティブなタスク一覧を取得する。重複タスク作成を防止するために、タスク作成前に確認すること。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
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
                        "description": "ゾーンID（省略時: 全ゾーン）"
                    }
                },
                "required": []
            }
        }
    }
]


def get_tools():
    """Return all tool definitions for LLM."""
    return TOOLS


def get_tool_names():
    """Return list of all tool names."""
    return [t["function"]["name"] for t in TOOLS]
