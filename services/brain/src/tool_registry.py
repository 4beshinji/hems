"""
OpenAI function-calling tool definitions for HEMS Brain.
Base: create_task, send_device_command, get_zone_status, speak, get_active_tasks, get_device_status
OpenClaw: get_pc_status, run_pc_command, control_browser, send_pc_notification
Obsidian: search_notes, write_note, get_recent_notes
"""


def get_tools(openclaw_enabled: bool = False, services_enabled: bool = False,
              obsidian_enabled: bool = False, ha_enabled: bool = False,
              biometric_enabled: bool = False,
              perception_enabled: bool = False) -> list:
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
    ]

    if openclaw_enabled:
        tools.extend(_get_pc_tools())

    if services_enabled:
        tools.extend(_get_service_tools())

    if obsidian_enabled:
        tools.extend(_get_obsidian_tools())

    if ha_enabled:
        tools.extend(_get_ha_tools())

    if biometric_enabled:
        tools.extend(_get_biometric_tools())

    if perception_enabled:
        tools.extend(_get_perception_tools())

    return tools


def get_tool_names(openclaw_enabled: bool = False, services_enabled: bool = False,
                   obsidian_enabled: bool = False, ha_enabled: bool = False,
                   biometric_enabled: bool = False,
                   perception_enabled: bool = False) -> list:
    """Return list of all enabled tool names."""
    return [t["function"]["name"] for t in get_tools(openclaw_enabled, services_enabled,
                                                      obsidian_enabled, ha_enabled,
                                                      biometric_enabled,
                                                      perception_enabled)]


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


def _get_obsidian_tools() -> list:
    """Obsidian knowledge base tools — only included when obsidian-bridge is configured."""
    return [
        {
            "type": "function",
            "function": {
                "name": "search_notes",
                "description": "Obsidianのノートをキーワード・タグ・パスで検索する。判断に追加コンテキストが必要な場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "検索キーワード"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "タグフィルター（例: ['daily', 'project']）",
                        },
                        "path_prefix": {"type": "string", "description": "パスプレフィックスフィルター（例: 'projects/'）"},
                        "max_results": {"type": "integer", "description": "最大結果数", "default": 5, "maximum": 10},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_note",
                "description": "HEMS/配下にメモを書き込む。学習結果・分析・記録の保存に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "ノートタイトル"},
                        "content": {"type": "string", "description": "ノート本文（Markdown）"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "タグ（例: ['hems', 'analysis']）",
                        },
                        "category": {"type": "string", "description": "カテゴリ（例: 'decisions', 'learnings'）"},
                    },
                    "required": ["title", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_recent_notes",
                "description": "最近変更されたノートの一覧を取得する。ユーザーの最近の活動を把握する場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "取得件数", "default": 5, "maximum": 20},
                    },
                },
            },
        },
    ]


def _get_pc_tools() -> list:
    """PC tools — only included when OpenClaw bridge is configured."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_pc_status",
                "description": "PCのシステムメトリクス（CPU、メモリ、GPU、ディスク）を取得する。PC状態の確認に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "include_processes": {
                            "type": "boolean",
                            "description": "プロセスリストを含めるか",
                            "default": False,
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_pc_command",
                "description": "ホストPCでシェルコマンドを実行する。ファイル操作、状態確認、アプリ起動等に使用。危険なコマンドは禁止。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "実行するシェルコマンド"},
                        "cwd": {"type": "string", "description": "作業ディレクトリ（省略可）"},
                        "timeout": {"type": "number", "description": "タイムアウト秒数", "default": 30},
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "control_browser",
                "description": "ブラウザを操作する。URL遷移、JavaScript実行、現在のURL/タイトル取得が可能。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["navigate", "eval", "get_url", "get_title"],
                            "description": "ブラウザ操作の種類",
                        },
                        "url": {"type": "string", "description": "遷移先URL（navigate時）"},
                        "javascript": {"type": "string", "description": "実行するJS（eval時）"},
                    },
                    "required": ["action"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "send_pc_notification",
                "description": "デスクトップ通知を送信する。PCでの作業中に音声以外で通知したい場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "通知タイトル"},
                        "body": {"type": "string", "description": "通知本文"},
                        "priority": {
                            "type": "string",
                            "enum": ["active", "passive", "time-sensitive"],
                            "description": "通知優先度",
                            "default": "active",
                        },
                    },
                    "required": ["title", "body"],
                },
            },
        },
    ]


def _get_ha_tools() -> list:
    """Home Assistant tools — only included when HA bridge is configured."""
    return [
        {
            "type": "function",
            "function": {
                "name": "control_light",
                "description": "照明を制御する。ON/OFF、明るさ、色温度を設定可能。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "HA entity_id (例: light.living_room)"},
                        "on": {"type": "boolean", "description": "ON/OFF"},
                        "brightness": {"type": "integer", "description": "明るさ (0-255)", "minimum": 0, "maximum": 255},
                        "color_temp": {"type": "integer", "description": "色温度 (mirek, 153-500)", "minimum": 153, "maximum": 500},
                    },
                    "required": ["entity_id", "on"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "control_climate",
                "description": "エアコン・空調を制御する。モード、温度、風量を設定可能。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "HA entity_id (例: climate.living_room)"},
                        "mode": {
                            "type": "string",
                            "enum": ["off", "cool", "heat", "dry", "fan_only", "auto"],
                            "description": "運転モード",
                        },
                        "temperature": {"type": "number", "description": "設定温度 (16-30)", "minimum": 16, "maximum": 30},
                        "fan_mode": {
                            "type": "string",
                            "enum": ["auto", "low", "medium", "high"],
                            "description": "風量",
                        },
                    },
                    "required": ["entity_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "control_cover",
                "description": "カーテン・ブラインドを制御する。開閉またはポジション指定が可能。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "HA entity_id (例: cover.living_room)"},
                        "action": {
                            "type": "string",
                            "enum": ["open", "close", "stop"],
                            "description": "開閉操作",
                        },
                        "position": {"type": "integer", "description": "ポジション (0=閉, 100=全開)", "minimum": 0, "maximum": 100},
                    },
                    "required": ["entity_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_home_devices",
                "description": "スマートホームデバイスの状態一覧を取得する。照明、エアコン、カーテン等の現在の状態を確認する。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]


def _get_perception_tools() -> list:
    """Perception tools — only included when perception service is configured."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_perception_status",
                "description": "カメラベースの在室・姿勢・活動データを取得する。各ゾーンの人数、姿勢（standing/sitting/lying/walking）、活動レベルを確認できる。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]


def _get_biometric_tools() -> list:
    """Biometric tools — only included when biometric-bridge is configured."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_biometrics",
                "description": "心拍・SpO2・ストレス・疲労度・歩数などの生体データを取得する。ユーザーの体調確認に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_sleep_summary",
                "description": "直近の睡眠データ（時間・深い睡眠・REM・品質スコア）を取得する。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]
