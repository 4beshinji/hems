"""Grouped OpenAI tool schemas."""


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
        {
            "type": "function",
            "function": {
                "name": "list_scene_objects",
                "description": "過去のVLM観測履歴から指定ゾーンで確認された物体のユニークリストを取得する。短時間で複数回VLMを呼ばずに、過去N分間で何が見えていたかを確認したい場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zone_id": {"type": "string", "description": "ゾーンID"},
                        "since_minutes": {
                            "type": "integer",
                            "description": "何分前までの履歴を見るか (デフォルト60, 最大60)",
                            "default": 60,
                        },
                    },
                    "required": ["zone_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_scene_timeline",
                "description": "指定ゾーンのVLMシーン履歴を時系列で取得する。最新10件まで。シーンの変化を把握したい場合に使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zone_id": {"type": "string", "description": "ゾーンID"},
                    },
                    "required": ["zone_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_cameras",
                "description": (
                    "登録されているカメラの一覧と接続状態を取得する。カメラ毎の zone / type / connected を返す。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_vlm_status",
                "description": (
                    "VLM scheduler の現在状態 (light/heavy model 名、最後の処理時刻、保留中リクエスト数) を取得する。"
                    "VLM が応答しない / 遅い時に状態確認に使う。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_activity_history",
                "description": (
                    "指定ゾーンの活動レベル/姿勢履歴を時系列で取得する。"
                    "最近のVLMスナップショット (timestamp, scene_type, anomalies) を最新N件返す。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zone_id": {"type": "string", "description": "ゾーンID"},
                        "limit": {
                            "type": "integer",
                            "description": "返すスナップショットの最大件数 (デフォルト10)",
                            "minimum": 1,
                            "maximum": 30,
                            "default": 10,
                        },
                    },
                    "required": ["zone_id"],
                },
            },
        },
    ]
