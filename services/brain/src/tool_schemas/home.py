"""Grouped OpenAI tool schemas."""


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
        {
            "type": "function",
            "function": {
                "name": "get_entity_status",
                "description": (
                    "HAの単一エンティティ状態を即時取得する (read-only)。"
                    "バッテリ・接続状態・直近state変化の確認に使う。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "HA entity_id (例: light.living_room, sensor.battery_level)",
                        },
                    },
                    "required": ["entity_id"],
                },
            },
        },
    ]


def _get_tapo_tools() -> list:
    """Tapo bridge tools — only included when tapo-bridge is configured."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_power_consumption",
                "description": (
                    "Tapo P110/P115 スマートプラグの瞬時電力 (W) と直近の電圧/電流/累計消費電力を取得する。"
                    "「いま冷蔵庫いくら使ってる?」「ヒーター付けたら何W?」のような問いに使う。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "デバイスID (例: tapo.plug_desklight)。省略で全Tapoプラグの電力一覧を返す",
                        },
                    },
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
