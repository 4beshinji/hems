"""Grouped OpenAI tool schemas."""


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
