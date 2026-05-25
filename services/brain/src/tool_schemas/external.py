"""Grouped OpenAI tool schemas."""


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
        {
            "type": "function",
            "function": {
                "name": "list_note_tags",
                "description": (
                    "Obsidian Vault に存在するタグ一覧と各タグの使用回数を取得する。"
                    "テーマや関心領域の俯瞰、関連ノートの検索キーワード選びに使う。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]


def _get_gas_tools() -> list:
    """GAS bridge tools (read-only) — only included when gas-bridge is configured."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_recent_emails",
                "description": (
                    "最近のGmailスレッド一覧を取得する (read-only)。"
                    "サマリ件数だけでは不足な場合や、特定の送信者・件名を確認する際に使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "返すスレッドの最大件数",
                            "minimum": 1,
                            "maximum": 50,
                            "default": 10,
                        },
                        "sender_contains": {
                            "type": "string",
                            "description": "送信者(from)に含まれる文字列でフィルタ (省略可)",
                        },
                        "subject_contains": {
                            "type": "string",
                            "description": "件名に含まれる文字列でフィルタ (省略可)",
                        },
                        "unread_only": {
                            "type": "boolean",
                            "description": "未読のみ返す",
                            "default": False,
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "gas_query_free_slots",
                "description": (
                    "カレンダーの空き時間スロット (HH:MM-HH:MM) を時刻つきで取得する (read-only)。"
                    "予定の合間に作業時間が必要な時、新規予定を提案する時に使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date_range_hours": {
                            "type": "integer",
                            "description": "今から何時間先まで探索するか",
                            "minimum": 1,
                            "maximum": 168,
                            "default": 24,
                        },
                        "min_duration_minutes": {
                            "type": "integer",
                            "description": "返すスロットの最小長 (分)",
                            "minimum": 15,
                            "maximum": 480,
                            "default": 60,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返すスロットの最大件数",
                            "minimum": 1,
                            "maximum": 20,
                            "default": 5,
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "gas_query_sheet",
                "description": (
                    "Google Sheets の指定タブを取得する (read-only)。"
                    "world_model.gas_state.sheets にキャッシュされたシートデータを返す。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "シート名 (タブ名)",
                        },
                        "max_rows": {
                            "type": "integer",
                            "description": "返す最大行数",
                            "minimum": 1,
                            "maximum": 200,
                            "default": 50,
                        },
                    },
                    "required": ["name"],
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
        {
            "type": "function",
            "function": {
                "name": "get_recent_knowledge_changes",
                "description": (
                    "ナレッジソースで最近変更されたドキュメント一覧を取得する。"
                    "ユーザーが直近に追加・編集した資料を察知して、それを起点にした提案や引用に使う。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "取得件数", "default": 10, "maximum": 50},
                        "source": {"type": "string", "description": "ソース名でフィルタ (省略可)"},
                    },
                },
            },
        },
    ]
