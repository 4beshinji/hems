"""Mock LLM for HEMS development/testing.

OpenAI-compatible chat completion API that responds with keyword-matched
tool calls (Brain mode) or natural text (Voice text gen mode).
Adapted for single-occupant home environment.
"""

from fastapi import FastAPI, Request
import json
import uuid
import re
import random

app = FastAPI(title="HEMS Mock LLM")


def _make_tool_call(name: str, arguments: dict) -> dict:
    return {
        "id": f"call_{uuid.uuid4().hex[:8]}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        }
    }


def _handle_voice_generation(full_text: str) -> dict:
    """Handle text generation requests from voice service (no tools)."""
    # Task announcement: extract title from prompt
    title_match = re.search(r"タイトル:\s*(.+)", full_text)
    task_title = title_match.group(1).strip() if title_match else ""

    # Completion text
    if "完了しました" in full_text or "完了への感謝" in full_text:
        if task_title:
            return _response(content=f"ありがとうございます！{task_title}、お疲れさまでした。")
        return _response(content="ありがとうございます！お疲れさまでした。")

    # Feedback
    if "感謝を" in full_text or "お礼" in full_text or "励まし" in full_text:
        return _response(content="ありがとうございます！おかげで快適な環境が保たれています。")

    # Task announcement text
    if task_title:
        zone_match = re.search(r"エリア:\s*(.+)", full_text)
        zone = zone_match.group(1).strip() if zone_match else ""
        xp_match = re.search(r"XP:\s*(\d+)", full_text)
        xp = xp_match.group(1) if xp_match else "0"
        location = f"{zone}で" if zone and zone != "不明" else ""
        return _response(content=f"お願いがあります。{location}{task_title}。{xp}XPを獲得できます。")

    # Generic fallback
    return _response(content="承知しました。対応をお願いします。")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    tools = body.get("tools", [])

    full_text = " ".join([m.get("content", "") or "" for m in messages]).lower()

    # Voice service requests: no tools provided
    if not tools:
        return _handle_voice_generation(full_text)

    # Follow-up with tool results -> completion
    has_tool_results = any(m.get("role") == "tool" for m in messages)
    if has_tool_results:
        return _response(content="対応を実行しました。状況を引き続き監視します。")

    # --- Home environment keyword matching ---

    # High temperature
    if ("温度" in full_text or "気温" in full_text or "temperature" in full_text) and (
        "高" in full_text or "暑" in full_text or "30" in full_text
    ):
        return _response(
            content="高温を検知しました。タスクを作成します。",
            tool_calls=[
                _make_tool_call("create_task", {
                    "title": "エアコンをつけてください",
                    "description": "室温が高くなっています。エアコンの電源を入れて室温を下げてください。",
                    "xp_reward": 100,
                    "urgency": 3,
                    "task_types": "environment,urgent",
                })
            ]
        )

    # High CO2
    if ("co2" in full_text or "二酸化炭素" in full_text) and (
        "換気" in full_text or "1000" in full_text or "超" in full_text
    ):
        return _response(
            content="CO2濃度が高いです。換気タスクを作成します。",
            tool_calls=[
                _make_tool_call("create_task", {
                    "title": "窓を開けて換気してください",
                    "description": "CO2濃度が基準値を超えています。窓を開けて換気してください。",
                    "xp_reward": 80,
                    "urgency": 2,
                    "task_types": "environment",
                })
            ]
        )

    # Low humidity
    if ("湿度" in full_text or "humidity" in full_text) and (
        "低" in full_text or "乾燥" in full_text
    ):
        return _response(
            content="低湿度を検知しました。加湿タスクを作成します。",
            tool_calls=[
                _make_tool_call("create_task", {
                    "title": "加湿器をつけてください",
                    "description": "室内が乾燥しています。加湿器を稼働させてください。",
                    "xp_reward": 80,
                    "urgency": 2,
                    "task_types": "environment",
                })
            ]
        )

    # Sedentary alert -> speak caring
    if "sedentary" in full_text or "座り" in full_text or "長時間" in full_text:
        messages_list = [
            "ずっと座りっぱなしみたいですね。少し立ち上がってストレッチしませんか？",
            "そろそろ休憩しましょう。立ち上がって体を動かしてください。",
            "長時間お疲れさまです。少し歩いてリフレッシュしませんか？",
        ]
        return _response(
            content="長時間の着座を検知しました。声をかけます。",
            tool_calls=[
                _make_tool_call("speak", {
                    "message": random.choice(messages_list),
                    "tone": "caring",
                })
            ]
        )

    # Calendar reminder
    if "予定" in full_text or "カレンダー" in full_text or "calendar" in full_text:
        return _response(
            content="予定のリマインドをします。",
            tool_calls=[
                _make_tool_call("speak", {
                    "message": "もうすぐ予定の時間です。準備はできていますか？",
                    "tone": "neutral",
                })
            ]
        )

    # Training / exercise recommendation
    if "トレーニング" in full_text or "疲労" in full_text or "tsb" in full_text:
        return _response(
            content="トレーニング状態を確認しました。",
            tool_calls=[
                _make_tool_call("speak", {
                    "message": "今日はレスト日にしましょう。体の回復を優先してください。",
                    "tone": "caring",
                })
            ]
        )

    # Heart rate / biometrics alert
    if "心拍" in full_text or "heart_rate" in full_text or "hrv" in full_text:
        return _response(
            content="生体情報の変化を検知しました。",
            tool_calls=[
                _make_tool_call("speak", {
                    "message": "少しリラックスしましょう。深呼吸を3回してみてください。",
                    "tone": "caring",
                })
            ]
        )

    # Normal status
    return _response(content="現在の環境は正常範囲内です。特に対応の必要はありません。")


def _response(content: str, tool_calls: list = None) -> dict:
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
        finish_reason = "tool_calls"
    else:
        finish_reason = "stop"

    return {
        "id": f"mock-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "mock-hems",
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": finish_reason,
        }],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 10,
            "total_tokens": 20,
        }
    }
