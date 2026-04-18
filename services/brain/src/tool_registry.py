"""
OpenAI function-calling tool definitions for HEMS Brain.
Base: create_task, send_device_command, get_zone_status, speak, get_active_tasks, get_device_status
localcraw: get_pc_status, run_pc_command, control_browser, send_pc_notification
Obsidian: search_notes, write_note, get_recent_notes
Knowledge: search_knowledge, get_knowledge_sources, read_knowledge_document
"""


def get_tools(
    openclaw_enabled: bool = False,
    services_enabled: bool = False,
    obsidian_enabled: bool = False,
    ha_enabled: bool = False,
    biometric_enabled: bool = False,
    perception_enabled: bool = False,
    shopping_enabled: bool = False,
    switchbot_enabled: bool = False,
    news_enabled: bool = False,
    knowledge_enabled: bool = False,
    device_registry_enabled: bool = True,
) -> list:
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
    ]

    if openclaw_enabled:
        tools.extend(_get_pc_tools())

    if services_enabled:
        tools.extend(_get_service_tools())

    if obsidian_enabled:
        tools.extend(_get_obsidian_tools())

    if ha_enabled:
        tools.extend(_get_ha_tools())
        tools.extend(_get_system_tools())

    if biometric_enabled:
        tools.extend(_get_biometric_tools())

    if perception_enabled:
        tools.extend(_get_perception_tools())

    if shopping_enabled:
        tools.extend(_get_shopping_tools())

    if switchbot_enabled:
        tools.extend(_get_switchbot_tools())

    if news_enabled:
        tools.extend(_get_news_tools())

    if knowledge_enabled:
        tools.extend(_get_knowledge_tools())

    if device_registry_enabled:
        tools.extend(_get_device_registry_tools())
        tools.extend(_get_scene_tools())

    return tools


def get_chat_tools(
    openclaw_enabled: bool = False,
    services_enabled: bool = False,
    obsidian_enabled: bool = False,
    ha_enabled: bool = False,
    biometric_enabled: bool = False,
    perception_enabled: bool = False,
    switchbot_enabled: bool = False,
    news_enabled: bool = False,
    knowledge_enabled: bool = False,
    device_registry_enabled: bool = True,
) -> list:
    """Return read-only tool subset for conversational chat.

    Excludes action tools: create_task, speak, send_device_command, control_*,
    write_note, add_shopping_item, run_pc_command, etc.
    """
    # Read-only tool names allowed in chat
    _CHAT_ALLOWED = {
        "get_zone_status",
        "get_active_tasks",
        "get_device_status",
        "get_pc_status",
        "get_service_status",
        "search_notes",
        "get_recent_notes",
        "get_home_devices",
        "get_sensor_data",
        "get_weather",
        "get_biometrics",
        "get_sleep_summary",
        "get_perception_status",
        "get_shopping_list",
        "get_switchbot_devices",
        "get_news_summary",
        "search_knowledge",
        "get_knowledge_sources",
        "read_knowledge_document",
        "list_devices",
        "describe_device",
        "control_actuator",
        "list_scenes",
    }

    all_tools = get_tools(
        openclaw_enabled=openclaw_enabled,
        services_enabled=services_enabled,
        obsidian_enabled=obsidian_enabled,
        ha_enabled=ha_enabled,
        biometric_enabled=biometric_enabled,
        perception_enabled=perception_enabled,
        device_registry_enabled=device_registry_enabled,
        shopping_enabled=True,
        switchbot_enabled=switchbot_enabled,
        news_enabled=news_enabled,
        knowledge_enabled=knowledge_enabled,
    )
    return [t for t in all_tools if t["function"]["name"] in _CHAT_ALLOWED]


def get_tool_names(
    openclaw_enabled: bool = False,
    services_enabled: bool = False,
    obsidian_enabled: bool = False,
    ha_enabled: bool = False,
    biometric_enabled: bool = False,
    perception_enabled: bool = False,
    shopping_enabled: bool = False,
    switchbot_enabled: bool = False,
    news_enabled: bool = False,
    knowledge_enabled: bool = False,
) -> list:
    """Return list of all enabled tool names."""
    return [
        t["function"]["name"]
        for t in get_tools(
            openclaw_enabled,
            services_enabled,
            obsidian_enabled,
            ha_enabled,
            biometric_enabled,
            perception_enabled,
            shopping_enabled,
            switchbot_enabled,
            news_enabled,
            knowledge_enabled,
        )
    ]


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
                        "path_prefix": {
                            "type": "string",
                            "description": "パスプレフィックスフィルター（例: 'projects/'）",
                        },
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
                        "brightness": {
                            "type": "integer",
                            "description": "明るさ (0-255)",
                            "minimum": 0,
                            "maximum": 255,
                        },
                        "color_temp": {
                            "type": "integer",
                            "description": "色温度 (mirek, 153-500)",
                            "minimum": 153,
                            "maximum": 500,
                        },
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
                        "temperature": {
                            "type": "number",
                            "description": "設定温度 (16-30)",
                            "minimum": 16,
                            "maximum": 30,
                        },
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
                        "position": {
                            "type": "integer",
                            "description": "ポジション (0=閉, 100=全開)",
                            "minimum": 0,
                            "maximum": 100,
                        },
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
        {
            "type": "function",
            "function": {
                "name": "control_switch",
                "description": "スイッチをON/OFFする。スマートプラグ、家電の電源制御に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "HA entity_id (例: switch.plug_washer)"},
                        "on": {"type": "boolean", "description": "ON/OFF"},
                    },
                    "required": ["entity_id", "on"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_sensor_data",
                "description": "HAセンサーの値を取得する。電力、CO2、PM2.5等の数値データを確認する。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "特定のsensor entity_id（省略で全件）"},
                        "device_class": {
                            "type": "string",
                            "description": "デバイスクラスでフィルタ（例: power, carbon_dioxide, pm25）",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_scene",
                "description": "HAシーンを実行する。事前定義された複数デバイスの一括操作に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "HA scene entity_id (例: scene.good_night)"},
                    },
                    "required": ["entity_id"],
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
        {
            "type": "function",
            "function": {
                "name": "describe_scene",
                "description": "カメラ映像をVLMで分析しシーン詳細を取得する。部屋の状態、物体、異常を詳細に把握したい場合に使用。VLMは応答に数秒かかるため頻繁に呼ばないこと。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zone_id": {
                            "type": "string",
                            "description": "ゾーンID（省略時: 全ゾーン）",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "カスタム質問（省略時: 一般的なシーン説明）",
                        },
                    },
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


def _get_news_tools() -> list:
    """News tools — only included when news-bridge is configured."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_news_summary",
                "description": "最新のニュースサマリを取得する。ユーザーがニュースを尋ねた場合や、ニュース速報の詳細を確認する場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]


def _get_switchbot_tools() -> list:
    """SwitchBot tools — only included when switchbot-bridge is configured."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_switchbot_devices",
                "description": "SwitchBotデバイスの一覧と状態を取得する。照明・カーテン・プラグ・センサー等の確認に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "control_switchbot",
                "description": "SwitchBotデバイスにコマンドを送信する。照明ON/OFF、カーテン開閉、プラグ制御等に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_id": {"type": "string", "description": "SwitchBotデバイスID"},
                        "command": {
                            "type": "string",
                            "description": "コマンド (例: turnOn, turnOff, toggle, setBrightness, setPosition, setColorTemperature, press)",
                        },
                        "parameter": {
                            "type": "string",
                            "description": "パラメータ (例: brightness=50, position=0,1,80, colorTemp=3500)。不要な場合は省略。",
                            "default": "default",
                        },
                    },
                    "required": ["device_id", "command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "send_switchbot_ir",
                "description": "SwitchBot Hub経由で赤外線コマンドを送信する。エアコン・テレビ等のIRリモコン制御に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "IRデバイスID（SwitchBotアプリで登録した仮想デバイス）",
                        },
                        "command": {
                            "type": "string",
                            "description": "コマンド (例: turnOn, turnOff, setAll)",
                        },
                        "parameter": {
                            "type": "string",
                            "description": "パラメータ (例: エアコン setAll の場合 '26,1,3,on' = 温度,モード,風速,電源)",
                            "default": "default",
                        },
                    },
                    "required": ["device_id", "command"],
                },
            },
        },
    ]


def _get_knowledge_tools() -> list:
    """Knowledge base tools — only included when knowledge-bridge is configured."""
    return [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge",
                "description": "研究ノート・論文・コードなど外部ナレッジソースを横断検索する。判断に研究コンテキストが必要な場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "検索キーワード"},
                        "source": {"type": "string", "description": "ソース名でフィルタ（例: 'pws'）"},
                        "doc_type": {
                            "type": "string",
                            "enum": ["markdown", "python", "json", "text", "pdf", "docx", "csv", "html"],
                            "description": "ドキュメント種別フィルタ",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "タグフィルター",
                        },
                        "max_results": {"type": "integer", "description": "最大結果数", "default": 5, "maximum": 20},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_knowledge_sources",
                "description": "利用可能なナレッジソース一覧と統計を取得する。何が検索可能か確認する場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_knowledge_document",
                "description": "特定のナレッジドキュメントを読み込む。search_knowledgeの結果から詳細を確認する場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "ソース名"},
                        "path": {"type": "string", "description": "ドキュメントパス"},
                    },
                    "required": ["source", "path"],
                },
            },
        },
    ]


def _get_scene_tools() -> list:
    """Scene tools — execute predefined multi-device action sequences."""
    return [
        {
            "type": "function",
            "function": {
                "name": "execute_scene_by_name",
                "description": (
                    "事前定義されたシーン (programmatic name) を実行する。"
                    "例: wake_up → デスクライトON→IRシーリング→電球段階点灯。"
                    "HAのexecute_sceneとは別 (HA scene は entity_id.* を使う)。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "シーンのprogrammatic name (例: wake_up, bedtime)",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_scenes",
                "description": "登録済みの有効シーン一覧を取得する。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def _get_device_registry_tools() -> list:
    """Unified sensor + actuator tools via Device Registry (vendor-agnostic).

    control_actuator dispatches by Device.vendor to the appropriate bridge/MQTT.
    Use list_devices to discover devices by purpose/zone/capability.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "control_actuator",
                "description": (
                    "登録済みデバイスに制御コマンドを送る（ベンダー非依存）。"
                    "list_devicesで対象を確認してからdevice_idを指定。"
                    "actionは on/off/toggle/set_brightness/set_color_temp/set_color_xy/"
                    "set_color_hs/set_position/set_temperature/pulse/rainbow/ir_send。"
                    "pulseは指定秒数ONにしてから自動OFF（水ポンプ等に使う）。"
                    "rainbowは色相を虹色に循環させる（カラーLED専用、最大60秒）。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "デバイスID (例: tapo.plug_desklight, zigbee.bulb_bedroom)",
                        },
                        "action": {
                            "type": "string",
                            "enum": [
                                "on",
                                "off",
                                "toggle",
                                "set_brightness",
                                "set_color_temp",
                                "set_color_xy",
                                "set_color_hs",
                                "set_position",
                                "set_temperature",
                                "pulse",
                                "rainbow",
                                "ir_send",
                            ],
                            "description": "アクション種別",
                        },
                        "params": {
                            "type": "object",
                            "description": (
                                "アクション引数。set_brightness={value:0-255}, "
                                "set_color_temp={value:153-500}, "
                                "set_color_xy={x:0.0-1.0, y:0.0-1.0}, "
                                "set_color_hs={hue:0-360, saturation:0-100}, "
                                "set_position={value:0-100}, "
                                "set_temperature={value:16-30}, pulse={duration_s:1-600}, "
                                "rainbow={duration_s:1-60}, "
                                "ir_send={command:str, parameter:str}"
                            ),
                        },
                    },
                    "required": ["device_id", "action"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_devices",
                "description": (
                    "登録済みデバイス一覧を取得する。用途・ゾーン・機能・種別でフィルタ可能。"
                    "actuator制御前に対象デバイスを特定するために使う。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["sensor", "actuator", "both"],
                            "description": "デバイス種別",
                        },
                        "zone": {"type": "string", "description": "ゾーン名フィルタ"},
                        "vendor": {
                            "type": "string",
                            "enum": ["zigbee", "switchbot", "tapo", "ha", "mcp", "ir_via_hub"],
                            "description": "ベンダーフィルタ",
                        },
                        "capability": {
                            "type": "string",
                            "enum": [
                                "on_off",
                                "brightness",
                                "color_temp",
                                "set_position",
                                "set_temperature",
                                "pulse",
                                "ir_send",
                            ],
                            "description": "機能フィルタ",
                        },
                        "purpose_contains": {
                            "type": "string",
                            "description": "用途テキスト部分一致フィルタ (例: '水やり', '起床')",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "describe_device",
                "description": (
                    "特定デバイスの詳細情報（メタデータ+現在状態+最新値）を取得する。"
                    "control_actuatorを呼ぶ前の現状確認に使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_id": {"type": "string", "description": "デバイスID"},
                    },
                    "required": ["device_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "zigbee_permit_join",
                "description": (
                    "Zigbee コーディネーターのペアリングモードを開閉する。"
                    "新しい Zigbee デバイス登録時のみ使用。安全のため duration_s は通常 60-120 秒。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "enable": {
                            "type": "boolean",
                            "description": "true=ペアリング開始, false=終了",
                        },
                        "duration_s": {
                            "type": "integer",
                            "description": "自動終了までの秒数 (0=手動終了, 最大3600)",
                            "minimum": 0,
                            "maximum": 3600,
                        },
                    },
                    "required": ["enable"],
                },
            },
        },
    ]
