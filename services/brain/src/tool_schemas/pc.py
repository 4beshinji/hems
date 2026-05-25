"""Grouped OpenAI tool schemas."""


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
                "name": "list_processes",
                "description": (
                    "PCで実行中のプロセスを取得する (read-only)。CPU/メモリを多く使うプロセスを特定する用途に使う。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "返すプロセス数",
                            "minimum": 1,
                            "maximum": 50,
                            "default": 10,
                        },
                        "sort_by": {
                            "type": "string",
                            "enum": ["cpu", "memory"],
                            "description": "ソート基準",
                            "default": "cpu",
                        },
                        "name_contains": {
                            "type": "string",
                            "description": "プロセス名フィルタ (省略可)",
                        },
                    },
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
