"""Grouped OpenAI tool schemas."""


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
        {
            "type": "function",
            "function": {
                "name": "get_biometric_trend",
                "description": (
                    "生体メトリックの履歴 (時系列) を取得する。傾向 (上昇/下降/平均/標準偏差) を判断したい場合に使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": [
                                "heart_rate",
                                "hrv",
                                "stress",
                                "fatigue",
                                "spo2",
                                "body_temperature",
                                "respiratory_rate",
                                "steps",
                            ],
                            "description": "対象メトリック",
                        },
                        "window_hours": {
                            "type": "number",
                            "description": "今から何時間遡るか",
                            "minimum": 1,
                            "maximum": 168,
                            "default": 24,
                        },
                        "max_samples": {
                            "type": "integer",
                            "description": "返す最大サンプル数 (オーバーする時は等間隔ダウンサンプル)",
                            "minimum": 10,
                            "maximum": 500,
                            "default": 100,
                        },
                    },
                    "required": ["metric"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_sleep_history",
                "description": (
                    "直近 N 日分の睡眠品質スコア / 睡眠時間履歴を取得する。"
                    "睡眠傾向の評価や、品質変化に基づいた助言の根拠に使う。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "遡る日数",
                            "minimum": 1,
                            "maximum": 14,
                            "default": 7,
                        },
                    },
                },
            },
        },
    ]
