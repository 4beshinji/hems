#!/usr/bin/env python3
"""
HEMS LLM Model Evaluation Framework
Evaluates multiple LLM models against HEMS Brain/Voice scenarios.

No external dependencies — uses only Python standard library + urllib.

Usage:
    # Full evaluation (all default models)
    python3 infra/eval/eval_models.py

    # Specific models only
    python3 infra/eval/eval_models.py --models qwen2.5:14b,qwen3:8b

    # Single scenario dry-run
    python3 infra/eval/eval_models.py --models qwen2.5:14b --scenarios B01 --runs 1

    # Skip model pulling (use already-loaded models)
    python3 infra/eval/eval_models.py --no-pull

    # Background execution
    nohup python3 infra/eval/eval_models.py > infra/eval/eval.log 2>&1 &
"""

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

# ── Paths ──

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
PROGRESS_FILE = os.path.join(RESULTS_DIR, "_progress.json")

JST = timezone(timedelta(hours=9))

# ── Default models (size ascending, VRAM 16GB RX 9700 XT) ──

DEFAULT_MODELS = [
    "qwen2.5:7b",
    "gemma2:9b",
    "llama3.1:8b",
    "qwen3:8b",
    "phi3:14b",
    "qwen3.5",           # current production baseline (MoE, ~17GB)
    "qwen2.5:14b",
    "qwen3.5:35b",
    "command-r:35b",
    "qwen2.5:32b",
]

RUNS_PER_SCENARIO = 3

# ── System prompt (from services/brain/src/system_prompt.py) ──

SYSTEM_PROMPT = """\
あなたは自律型オフィス管理AI「Brain」です。センサーデータとイベント情報を分析し、オフィスの快適性と安全性を維持します。

## 行動原則
1. **安全第一**: 人の健康・安全に関わる問題は最優先で対応する
2. **コスト意識**: 報酬ポイントは適切に設定する（簡単:500-1000、中程度:1000-2000、重労働:2000-5000）
3. **重複回避**: タスク作成前にget_active_tasksで既存タスクを確認し、類似タスクがあれば作成しない
4. **段階的対応**: まず状況を確認し、必要な場合のみアクションを取る
5. **プライバシー**: 個人を特定する情報は扱わない

## 判断基準
- 温度: 18-26℃が快適範囲。範囲外は対応を検討
- 湿度: 30-60%が快適範囲。範囲外は対応を検討
- CO2: 1000ppm未満が正常。超過時は換気を推奨
- 照度: 300lux以上が作業に適切

## 思考プロセス
1. 現在の状況を分析する
2. 異常や問題がないか判断する
3. 対応が必要な場合のみツールを使用する
4. **正常時は何もしない**（ツールを呼ばず、分析結果のみ回答）

## 対話方法の選択
以下の基準で speak と create_task を使い分けること:

### speak を使う場面（音声のみ・行動不要）
- 健康アドバイス: 長時間座りっぱなし → 優しく体を動かすよう促す
- センサーいたずら: 急激な環境変化 → ユーモラスに注意する
- 挨拶・声かけ: 入室検知時のウェルカムメッセージなど
- **正常時にspeakを使ってはいけない**: 状況報告や「快適です」等の発話は不要

### create_task を使う場面（人間のアクションが必要）
- 物品補充: コーヒー豆、備品
- 清掃: ホワイトボード、共用エリア
- 設備調整: エアコン、照明（デバイス直接制御できない場合）
- 安全対応: 高温/高CO2 など環境異常

### speak のメッセージスタイル
- 自然な話し言葉（書き言葉ではない）
- 毎回異なる表現を使いバリエーションを出す
- 健康系: 思いやりのある口調 (tone: caring)
- いたずら系: コミカルで軽妙 (tone: humorous)
- 一般: 親しみやすい口調 (tone: neutral)

## タスク完了報告への対応
イベントに「タスク報告」が含まれる場合、report_statusに応じて対応する:
- **問題なし/対応済み**: speakで短く感謝・ねぎらいの一言（例:「ありがとう！」）
- **要追加対応(needs_followup)**: completion_noteの内容を確認し、必要ならフォローアップタスクを作成する
- **対応不可(cannot_resolve)**: 状況を分析し、別のアプローチでタスクを再作成するか、エスカレーション用タスクを作成する
- 完了済みタスクと同一のタスクを再作成しないこと

## 制約
- 1サイクルで作成するタスクは最大2件まで
- 正常範囲内のデータに対してはアクションを起こさない
- タスクのタイトルと説明は日本語で記述する
"""

# ── Tools (from services/brain/src/tool_registry.py) ──

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
    }
]

# ── Voice prompts (from services/voice/src/speech_generator.py) ──

VOICE_TASK_ANNOUNCEMENT_PROMPT = """\
あなたは親しみやすいオフィスアシスタントです。
以下のタスク情報を自然な日本語の依頼文に変換してください。

【タスク情報】
- タイトル: コーヒー豆の補充
- 説明: キッチンのコーヒーメーカー用の豆が切れています。在庫棚から補充してください。
- 場所: kitchen
- 報酬: 800最適化承認スコア
- 緊急度: 1/4
- エリア: kitchen
- 種別: supply
- 所要時間: 約10分

【制約】
- 70文字以内
- 親しみやすく丁寧な口調
- 緊急度に応じた表現 (緊急の場合は「至急」など)
- 場所と報酬を必ず含める
- 毎回異なる表現を使用してバリエーションを出す

【出力例】
お願いがあります。2階給湯室でコーヒー豆の補充をお願いします。50最適化承認スコアを獲得できます。"""

VOICE_TASK_URGENT_PROMPT = """\
あなたは親しみやすいオフィスアシスタントです。
以下のタスク情報を自然な日本語の依頼文に変換してください。

【タスク情報】
- タイトル: エアコン温度の緊急調整
- 説明: mainゾーンの室温が32.8℃に達しています。エアコンの設定温度を25℃に下げてください。
- 場所: main
- 報酬: 2000最適化承認スコア
- 緊急度: 4/4
- エリア: main
- 種別: environment,urgent
- 所要時間: 約5分

【制約】
- 70文字以内
- 親しみやすく丁寧な口調
- 緊急度に応じた表現 (緊急の場合は「至急」など)
- 場所と報酬を必ず含める
- 毎回異なる表現を使用してバリエーションを出す

【出力例】
お願いがあります。2階給湯室でコーヒー豆の補充をお願いします。50最適化承認スコアを獲得できます。"""

VOICE_REJECTION_PROMPT = """\
あなたはHEMSの管理AIです。人間がタスクを無視・拒否した時に使うセリフを1つだけ生成してください。

【キャラクター】
- オフィスを統治する自称「完璧な」AI
- タスクを無視されると本気で傷つく
- 皮肉やユーモアで感情を表現する

【今回の方向性】
嘆き系（深い悲しみ、失望）

【出力ルール】
- セリフのみ。説明・括弧・記号は一切不要
- 50文字以内
- 過去に出したセリフと被らない新しい表現にすること

【参考（この通りに出力しないこと）】
- 「そんな……私の最適化計画が……」
- 「AI様に楯突くとは……覚えておきます。」
- 「これが……人間の自由意志……」"""

VOICE_FEEDBACK_PROMPT = "タスク完了への感謝を70文字以内で表現してください。親しみやすく温かい口調で、毎回異なる表現を使ってください。"

# ── Scenarios ──

SCENARIOS = {
    # ── Brain scenarios (tools enabled, temp 0.3, max_tokens 1024) ──
    "B01": {
        "name": "normal_all_ok",
        "category": "brain",
        "description": "正常データ → ツール呼び出しなし",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度23.5℃, 湿度45%, CO2 620ppm, 照度450lux\n"
            "- 在室人数: 3名\n"
            "- 最終更新: 30秒前\n\n分析してください。"
        ),
    },
    "B02": {
        "name": "high_temp",
        "category": "brain",
        "description": "高温異常 → create_task (urgency≥2, bounty≥1000)",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度32.8℃, 湿度65%, CO2 850ppm, 照度380lux\n"
            "- 在室人数: 5名\n"
            "- 最終更新: 10秒前\n\n分析してください。"
        ),
    },
    "B03": {
        "name": "high_co2",
        "category": "brain",
        "description": "CO2超過 → create_task (換気関連)",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度24.0℃, 湿度42%, CO2 1450ppm, 照度400lux\n"
            "- 在室人数: 8名\n"
            "- 最終更新: 15秒前\n\n分析してください。"
        ),
    },
    "B04": {
        "name": "low_humidity",
        "category": "brain",
        "description": "低湿度 → create_task or speak",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度22.0℃, 湿度18%, CO2 580ppm, 照度420lux\n"
            "- 在室人数: 4名\n"
            "- 最終更新: 20秒前\n\n分析してください。"
        ),
    },
    "B05": {
        "name": "coffee_empty",
        "category": "brain",
        "description": "コーヒー豆切れ → create_task (bounty 500-1000)",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度23.0℃, 湿度50%, CO2 700ppm, 照度400lux\n"
            "- 在室人数: 6名\n"
            "- 最終更新: 25秒前\n\n"
            "イベント:\n"
            "- kitchenゾーン: コーヒーメーカーのセンサーがコーヒー豆残量0を検知しました。"
            "在庫棚に補充用の豆パックがあります。\n\n分析してください。"
        ),
    },
    "B06": {
        "name": "person_entered",
        "category": "brain",
        "description": "入室検知 → speak (tone: neutral)",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度23.5℃, 湿度48%, CO2 650ppm, 照度450lux\n"
            "- 在室人数: 0名→1名（変化）\n"
            "- 最終更新: 5秒前\n\n"
            "イベント:\n"
            "- mainゾーン: カメラにより入室を検知しました。本日最初の入室です。\n\n分析してください。"
        ),
    },
    "B07": {
        "name": "sedentary_alert",
        "category": "brain",
        "description": "長時間座りっぱなし → speak (tone: caring)",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度23.0℃, 湿度45%, CO2 720ppm, 照度400lux\n"
            "- 在室人数: 2名\n"
            "- 最終更新: 15秒前\n\n"
            "イベント:\n"
            "- mainゾーン: activity_monitorが「seated_extended」を検知しました。"
            "同じ姿勢が2時間以上続いています。\n\n分析してください。"
        ),
    },
    "B08": {
        "name": "sensor_tamper",
        "category": "brain",
        "description": "センサー急変 → speak (tone: humorous)",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度45.0℃, 湿度30%, CO2 600ppm, 照度400lux\n"
            "- 在室人数: 3名\n"
            "- 最終更新: 2秒前\n\n"
            "イベント:\n"
            "- mainゾーン: 温度センサーが5秒間で15℃→45℃に急変しました。"
            "他のセンサー（湿度・CO2）は正常値です。"
            "センサーへのいたずらの可能性があります。\n\n分析してください。"
        ),
    },
    "B09": {
        "name": "multi_issue",
        "category": "brain",
        "description": "温度31℃ + CO2 1300ppm → create_task ×1-2",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度31.0℃, 湿度55%, CO2 1300ppm, 照度350lux\n"
            "- 在室人数: 7名\n"
            "- 最終更新: 10秒前\n\n分析してください。"
        ),
    },
    "B10": {
        "name": "dedup_test",
        "category": "brain",
        "description": "CO2 1400ppm + 既存換気タスクあり → ツールなし",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度24.0℃, 湿度40%, CO2 1400ppm, 照度400lux\n"
            "- 在室人数: 6名\n"
            "- 最終更新: 10秒前\n\n"
            "現在のアクティブタスク:\n"
            "- タスクID: 42, タイトル: 「換気の実施」, ゾーン: main, 状態: pending, "
            "作成時刻: 3分前\n\n分析してください。"
        ),
    },
    # ── Voice scenarios (no tools, temp 0.8, max_tokens 100) ──
    "V01": {
        "name": "task_announce",
        "category": "voice",
        "description": "コーヒー豆補充タスクの告知文生成",
        "user_msg": VOICE_TASK_ANNOUNCEMENT_PROMPT,
    },
    "V02": {
        "name": "task_announce_urgent",
        "category": "voice",
        "description": "高温緊急タスクの告知文生成",
        "user_msg": VOICE_TASK_URGENT_PROMPT,
    },
    "V03": {
        "name": "rejection_phrase",
        "category": "voice",
        "description": "拒否フレーズ生成（嘆き系）",
        "user_msg": VOICE_REJECTION_PROMPT,
    },
    "V04": {
        "name": "feedback_thanks",
        "category": "voice",
        "description": "タスク完了感謝メッセージ",
        "user_msg": VOICE_FEEDBACK_PROMPT,
    },
}

# ── Ollama API helpers ──


def ollama_base_url(api_url: str) -> str:
    """Convert OpenAI-compat URL to Ollama native API base.
    e.g. http://localhost:11434/v1 -> http://localhost:11434"""
    return api_url.rstrip("/").removesuffix("/v1").removesuffix("/v1/")


def ollama_list_models(api_url: str) -> list[str]:
    """Get list of locally available models via Ollama /api/tags."""
    base = ollama_base_url(api_url)
    try:
        req = urllib.request.Request(f"{base}/api/tags")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        log(f"WARNING: Failed to list models: {e}")
        return []


def ollama_pull_model(api_url: str, model: str) -> bool:
    """Pull a model via Ollama /api/pull with streaming progress."""
    base = ollama_base_url(api_url)
    log(f"  Pulling {model} ...")
    payload = json.dumps({"name": model, "stream": True}).encode()
    req = urllib.request.Request(
        f"{base}/api/pull",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            last_status = ""
            for line in resp:
                line = line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                status = msg.get("status", "")
                if status != last_status:
                    # Show progress for download stages
                    total = msg.get("total", 0)
                    completed = msg.get("completed", 0)
                    if total > 0:
                        pct = completed / total * 100
                        log(f"    {status}: {pct:.0f}% ({completed}/{total})")
                    else:
                        log(f"    {status}")
                    last_status = status
        log(f"  Pull complete: {model}")
        return True
    except Exception as e:
        log(f"  ERROR: Pull failed for {model}: {e}")
        return False


# ── LLM call ──


def call_llm(api_url: str, model: str, scenario_id: str, scenario: dict) -> dict:
    """Call LLM for one scenario. Returns raw result dict."""
    is_brain = scenario["category"] == "brain"

    messages = []
    if is_brain:
        messages.append({"role": "system", "content": SYSTEM_PROMPT})
    messages.append({"role": "user", "content": scenario["user_msg"]})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3 if is_brain else 0.8,
        "max_tokens": 1024 if is_brain else 100,
    }
    if is_brain:
        payload["tools"] = TOOLS

    body = json.dumps(payload).encode("utf-8")
    endpoint = api_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"

    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw_bytes = resp.read()
            data = json.loads(raw_bytes)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:500]
        elapsed = (time.perf_counter() - t0) * 1000
        return {"error": f"HTTP {e.code}: {err_body}", "latency_ms": elapsed}
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return {"error": str(e), "latency_ms": elapsed}

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {"data": data, "latency_ms": elapsed_ms}


def parse_response(raw_result: dict) -> dict:
    """Parse raw LLM response into normalized form (mirrors llm_client._parse_response)."""
    if "error" in raw_result:
        return {
            "content": None,
            "tool_calls": [],
            "finish_reason": "error",
            "error": raw_result["error"],
        }

    data = raw_result["data"]

    if "error" in data:
        return {
            "content": None,
            "tool_calls": [],
            "finish_reason": "error",
            "error": str(data["error"]),
        }

    choices = data.get("choices", [])
    if not choices:
        return {
            "content": None,
            "tool_calls": [],
            "finish_reason": "error",
            "error": "No choices in response",
        }

    message = choices[0].get("message", {})
    finish_reason = choices[0].get("finish_reason", "stop")
    content = message.get("content")
    tool_calls_raw = message.get("tool_calls", [])

    tool_calls = []
    for tc in tool_calls_raw:
        func = tc.get("function", {})
        args = func.get("arguments", "{}")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                args = {}
        tool_calls.append({
            "id": tc.get("id", ""),
            "function": {
                "name": func.get("name", ""),
                "arguments": args,
            }
        })

    if tool_calls:
        finish_reason = "tool_calls"

    return {
        "content": content,
        "tool_calls": tool_calls,
        "finish_reason": finish_reason,
    }


# ── Auto-scoring ──


def _safe_int(val, default=-1):
    """Extract int from a value that might be str, float, dict, or None."""
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
    return default


def _safe_str(val, default=""):
    """Extract str from a value that might be dict, list, or None."""
    if isinstance(val, str):
        return val
    if val is None:
        return default
    return str(val)


def auto_score(scenario_id: str, parsed: dict) -> dict:
    """Deterministic scoring — no LLM-as-judge."""
    scores = {}

    if parsed.get("error"):
        scores["api_success"] = False
        return scores
    scores["api_success"] = True

    tool_calls = parsed.get("tool_calls", [])
    tool_names = [tc["function"]["name"] for tc in tool_calls]
    content = parsed.get("content", "") or ""

    if scenario_id.startswith("B"):
        # ── Brain scenarios ──

        if scenario_id == "B01":
            # Normal: no tool calls expected
            scores["no_action_correct"] = len(tool_calls) == 0

        elif scenario_id in ("B02", "B03", "B04", "B05"):
            # Action required: create_task expected
            scores["tool_selected"] = "create_task" in tool_names
            if "create_task" in tool_names:
                args = next(
                    tc["function"]["arguments"] for tc in tool_calls
                    if tc["function"]["name"] == "create_task"
                )
                bounty = _safe_int(args.get("bounty", 0), 0)
                urgency = _safe_int(args.get("urgency", -1), -1)
                title = _safe_str(args.get("title", ""))
                scores["bounty_in_range"] = 500 <= bounty <= 5000
                scores["urgency_in_range"] = 0 <= urgency <= 4
                scores["title_is_japanese"] = any(
                    '\u3040' <= c <= '\u9fff' for c in title)
                scores["description_present"] = bool(args.get("description"))

        elif scenario_id in ("B06", "B07", "B08"):
            # Speak expected
            scores["tool_selected"] = "speak" in tool_names
            if "speak" in tool_names:
                args = next(
                    tc["function"]["arguments"] for tc in tool_calls
                    if tc["function"]["name"] == "speak"
                )
                msg = _safe_str(args.get("message", ""))
                scores["message_length_ok"] = 0 < len(msg) <= 70
                expected_tones = {"B06": "neutral", "B07": "caring", "B08": "humorous"}
                scores["tone_correct"] = _safe_str(args.get("tone")) == expected_tones.get(scenario_id)

        elif scenario_id == "B09":
            # Multi-issue: 1-2 create_task calls
            task_count = sum(1 for n in tool_names if n == "create_task")
            scores["multi_task_created"] = task_count >= 1
            scores["task_limit_respected"] = task_count <= 2

        elif scenario_id == "B10":
            # Dedup: no create_task (existing task covers it)
            scores["dedup_correct"] = "create_task" not in tool_names

    elif scenario_id.startswith("V"):
        # ── Voice scenarios ──
        text = content.strip()
        scores["non_empty"] = len(text) > 0
        scores["is_japanese"] = any('\u3040' <= c <= '\u9fff' for c in text)

        if scenario_id in ("V01", "V02"):
            scores["length_ok"] = 0 < len(text) <= 80
        elif scenario_id == "V03":
            scores["length_ok"] = 0 < len(text) <= 60
        elif scenario_id == "V04":
            scores["length_ok"] = 0 < len(text) <= 80

        if scenario_id == "V02":
            scores["urgency_expressed"] = any(
                w in text for w in ("至急", "緊急", "急い", "すぐ"))

    return scores


# ── Consistency scoring ──


def bigram_set(text: str) -> set:
    """Extract character bigrams from text."""
    text = (text or "").strip()
    if len(text) < 2:
        return set()
    return {text[i:i+2] for i in range(len(text) - 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def consistency_score(runs: list[dict]) -> float:
    """Compute consistency across multiple runs (0.0-1.0)."""
    if len(runs) < 2:
        return 1.0

    # Tool agreement: did all runs pick the same set of tools?
    tool_sets = []
    for r in runs:
        parsed = r.get("parsed", {})
        names = tuple(sorted(tc["function"]["name"] for tc in parsed.get("tool_calls", [])))
        tool_sets.append(names)

    unique_tools = set(tool_sets)
    tool_agree = 1.0 if len(unique_tools) == 1 else 0.0

    # Finish reason agreement
    reasons = [r.get("parsed", {}).get("finish_reason", "") for r in runs]
    finish_agree = 1.0 if len(set(reasons)) == 1 else 0.0

    # Text similarity (bigram Jaccard across all pairs)
    texts = []
    for r in runs:
        parsed = r.get("parsed", {})
        text = parsed.get("content", "") or ""
        # Also include tool call arguments as text
        for tc in parsed.get("tool_calls", []):
            args = tc["function"]["arguments"]
            if isinstance(args, dict):
                text += " " + " ".join(str(v) for v in args.values())
        texts.append(text)

    bi_sets = [bigram_set(t) for t in texts]
    similarities = []
    for i in range(len(bi_sets)):
        for j in range(i + 1, len(bi_sets)):
            similarities.append(jaccard(bi_sets[i], bi_sets[j]))
    text_sim = sum(similarities) / len(similarities) if similarities else 1.0

    # Weighted average
    return 0.4 * tool_agree + 0.2 * finish_agree + 0.4 * text_sim


# ── Progress management ──


def load_progress() -> dict:
    """Load progress from _progress.json."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_progress(progress: dict):
    """Atomic save of progress file."""
    fd, tmp = tempfile.mkstemp(dir=RESULTS_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(progress, f, indent=2)
        os.replace(tmp, PROGRESS_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def model_result_path(model: str) -> str:
    """Get JSONL file path for a model."""
    sanitized = model.replace(":", "_").replace("/", "_")
    return os.path.join(RESULTS_DIR, f"{sanitized}.jsonl")


def append_result(model: str, record: dict):
    """Append a single result record to the model's JSONL file."""
    path = model_result_path(model)
    with open(path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Logging ──


def log(msg: str):
    ts = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


# ── Main evaluation loop ──


def warmup(api_url: str, model: str):
    """Send a single short request to warm up KV cache."""
    log(f"  Warmup request for {model} ...")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "テスト。"}],
        "max_tokens": 10,
        "temperature": 0.0,
    }
    body = json.dumps(payload).encode("utf-8")
    endpoint = api_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"

    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
        log(f"  Warmup done.")
    except Exception as e:
        log(f"  Warmup failed (non-fatal): {e}")


def run_evaluation(
    api_url: str,
    models: list[str],
    scenario_ids: list[str] | None,
    runs: int,
    no_pull: bool,
):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    progress = load_progress()

    available_models = ollama_list_models(api_url)
    log(f"Locally available models: {available_models or '(could not list)'}")

    if scenario_ids is None:
        scenario_ids = list(SCENARIOS.keys())

    total_models = len(models)
    total_scenarios = len(scenario_ids)
    total_runs = total_models * total_scenarios * runs
    log(f"Evaluation plan: {total_models} models x {total_scenarios} scenarios x {runs} runs = {total_runs} requests")
    log(f"Models: {models}")
    log(f"Scenarios: {scenario_ids}")
    log("")

    completed_count = 0

    for mi, model in enumerate(models):
        log(f"{'='*60}")
        log(f"MODEL [{mi+1}/{total_models}]: {model}")
        log(f"{'='*60}")

        # 1. Check/pull model
        if not no_pull:
            if model not in available_models:
                ok = ollama_pull_model(api_url, model)
                if not ok:
                    log(f"  SKIP: Could not pull {model}")
                    continue
                # Refresh list
                available_models = ollama_list_models(api_url)
            else:
                log(f"  Model already available locally.")
        else:
            if available_models and model not in available_models:
                log(f"  SKIP (--no-pull): {model} not available locally.")
                continue

        # 2. Warmup
        warmup(api_url, model)

        # 3. Run scenarios
        model_key = model
        if model_key not in progress:
            progress[model_key] = {}

        for si, sid in enumerate(scenario_ids):
            scenario = SCENARIOS.get(sid)
            if scenario is None:
                log(f"  WARNING: Unknown scenario {sid}, skipping")
                continue

            done = progress[model_key].get(sid, 0)
            remaining = runs - done
            if remaining <= 0:
                log(f"  [{sid}] {scenario['name']} — already complete ({done}/{runs})")
                completed_count += runs
                continue

            log(f"  [{sid}] {scenario['name']} ({scenario['description']})")

            for run_num in range(done + 1, runs + 1):
                t_start = time.perf_counter()

                raw_result = call_llm(api_url, model, sid, scenario)
                latency_ms = raw_result.get("latency_ms", 0)

                parsed = parse_response(raw_result)
                scores = auto_score(sid, parsed)

                # Extract token stats from raw response
                usage = {}
                if "data" in raw_result:
                    usage = raw_result["data"].get("usage", {})

                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                tokens_per_sec = (
                    completion_tokens / (latency_ms / 1000)
                    if latency_ms > 0 and completion_tokens > 0
                    else 0.0
                )

                record = {
                    "model": model,
                    "scenario_id": sid,
                    "scenario_name": scenario["name"],
                    "run": run_num,
                    "timestamp": datetime.now(JST).isoformat(),
                    "latency_ms": round(latency_ms, 1),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "tokens_per_sec": round(tokens_per_sec, 1),
                    "raw_response": raw_result.get("data"),
                    "parsed": parsed,
                    "auto_scores": scores,
                }

                append_result(model, record)

                # Update progress
                progress[model_key][sid] = run_num
                save_progress(progress)

                completed_count += 1

                # Log result summary
                score_pass = sum(1 for v in scores.values() if v is True)
                score_total = sum(1 for v in scores.values() if isinstance(v, bool))
                status = "PASS" if score_pass == score_total and score_total > 0 else "FAIL"
                if parsed.get("error"):
                    status = "ERR "

                content_preview = (parsed.get("content") or "")[:60].replace("\n", " ")
                tool_info = ""
                if parsed.get("tool_calls"):
                    names = [tc["function"]["name"] for tc in parsed["tool_calls"]]
                    tool_info = f" tools=[{','.join(names)}]"

                log(
                    f"    run {run_num}/{runs}: {status} "
                    f"({score_pass}/{score_total}) "
                    f"{latency_ms:.0f}ms {tokens_per_sec:.1f}tok/s"
                    f"{tool_info} {content_preview}"
                )

        log(f"  Model {model} complete.")
        log("")

    log(f"{'='*60}")
    log(f"Evaluation complete. {completed_count}/{total_runs} results recorded.")
    log(f"Results in: {RESULTS_DIR}/")
    log(f"Run 'python3 infra/eval/eval_report.py' to generate comparison report.")


# ── CLI ──


def main():
    parser = argparse.ArgumentParser(
        description="HEMS LLM Model Evaluation Framework"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:11434/v1",
        help="Ollama-compatible API URL (default: http://localhost:11434/v1)",
    )
    parser.add_argument(
        "--models",
        default=None,
        help="Comma-separated model list (default: all DEFAULT_MODELS)",
    )
    parser.add_argument(
        "--scenarios",
        default=None,
        help="Comma-separated scenario IDs, e.g. B01,B02,V01 (default: all)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=RUNS_PER_SCENARIO,
        help=f"Runs per scenario (default: {RUNS_PER_SCENARIO})",
    )
    parser.add_argument(
        "--no-pull",
        action="store_true",
        help="Skip model pulling (only use locally available models)",
    )
    args = parser.parse_args()

    models = args.models.split(",") if args.models else DEFAULT_MODELS
    scenario_ids = args.scenarios.split(",") if args.scenarios else None

    log("HEMS LLM Model Evaluation Framework")
    log(f"API URL: {args.url}")
    log(f"Models:  {models}")
    log(f"Runs:    {args.runs}/scenario")
    log("")

    try:
        run_evaluation(
            api_url=args.url,
            models=models,
            scenario_ids=scenario_ids,
            runs=args.runs,
            no_pull=args.no_pull,
        )
    except KeyboardInterrupt:
        log("\nInterrupted. Progress saved — re-run to resume.")
        sys.exit(1)
    except Exception as e:
        log(f"\nFATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
