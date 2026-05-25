"""Grouped OpenAI tool schemas."""


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
