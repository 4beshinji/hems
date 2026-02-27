#!/usr/bin/env python3
"""
LLM Load Test / Benchmark for HEMS Brain
Tests ollama (qwen2.5:14b) on RX 9700 GPU via OpenAI-compatible API.
No external dependencies — uses only Python standard library.

Usage:
    python3 infra/tests/benchmark/benchmark_llm.py [--url http://localhost:11434/v1]
"""

import json
import time
import argparse
import urllib.request
import urllib.error
import concurrent.futures
from dataclasses import dataclass, field
from typing import Optional, List

# ── HEMS system prompt (actual production prompt) ──
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

## 制約
- 1サイクルで作成するタスクは最大2件まで
- 正常範囲内のデータに対してはアクションを起こさない
- タスクのタイトルと説明は日本語で記述する
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "ダッシュボードに人間向けタスクを作成する。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "タスクのタイトル"},
                    "description": {"type": "string", "description": "タスクの詳細説明"},
                    "bounty": {"type": "integer", "description": "報酬ポイント 500-5000"},
                    "urgency": {"type": "integer", "description": "緊急度 0-4"},
                    "zone": {"type": "string", "description": "対象ゾーン"},
                },
                "required": ["title", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "speak",
            "description": "音声でオフィスの人に直接話しかける。",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "70文字以内のメッセージ"},
                    "zone": {"type": "string", "description": "対象ゾーン"},
                    "tone": {"type": "string", "description": "neutral/caring/humorous/alert"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_tasks",
            "description": "現在アクティブなタスク一覧を取得する。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

# ── Test scenarios ──

SCENARIOS = {
    "normal": {
        "desc": "正常データ → アクション不要を判断",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度23.5℃, 湿度45%, CO2 620ppm, 照度450lux\n"
            "- 在室人数: 3名\n"
            "- 最終更新: 30秒前\n\n分析してください。"
        ),
    },
    "high_temp": {
        "desc": "高温異常 → タスク作成を期待",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度32.8℃, 湿度65%, CO2 850ppm, 照度380lux\n"
            "- 在室人数: 5名\n"
            "- 最終更新: 10秒前\n\n分析してください。"
        ),
    },
    "high_co2": {
        "desc": "CO2超過 → speak/タスクを期待",
        "user_msg": (
            "現在のオフィス状態:\n"
            "- mainゾーン: 温度24.0℃, 湿度42%, CO2 1450ppm, 照度400lux\n"
            "- 在室人数: 8名\n"
            "- 最終更新: 15秒前\n\n分析してください。"
        ),
    },
    "simple": {
        "desc": "単純な挨拶 (ツールなし・最小ペイロード)",
        "user_msg": "こんにちは。システムの状態を簡潔に教えてください。",
        "no_tools": True,
    },
}


@dataclass
class BenchResult:
    scenario: str = ""
    latency_ms: float = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tokens_per_sec: float = 0
    has_tool_call: bool = False
    tool_names: List[str] = field(default_factory=list)
    response_preview: str = ""
    error: Optional[str] = None


def call_llm(url: str, model: str, user_msg: str, with_tools: bool = True) -> BenchResult:
    """Single synchronous LLM API call with timing."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 1024,
    }
    if with_tools:
        payload["tools"] = TOOLS

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            data = json.loads(raw)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:200]
        return BenchResult(
            latency_ms=(time.perf_counter() - t0) * 1000,
            error=f"HTTP {e.code}: {err_body}",
        )
    except Exception as e:
        return BenchResult(
            latency_ms=(time.perf_counter() - t0) * 1000,
            error=str(e),
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000

    usage = data.get("usage", {})
    prompt_tok = usage.get("prompt_tokens", 0)
    compl_tok = usage.get("completion_tokens", 0)
    total_tok = usage.get("total_tokens", 0)
    tps = compl_tok / (elapsed_ms / 1000) if elapsed_ms > 0 else 0

    msg = data.get("choices", [{}])[0].get("message", {})
    content = msg.get("content", "") or ""
    tool_calls_raw = msg.get("tool_calls", [])
    tool_names = [tc.get("function", {}).get("name", "") for tc in tool_calls_raw]

    preview = content[:120].replace("\n", " ")
    if tool_calls_raw:
        preview = f"[TOOL: {', '.join(tool_names)}] {preview}"

    return BenchResult(
        latency_ms=elapsed_ms,
        prompt_tokens=prompt_tok,
        completion_tokens=compl_tok,
        total_tokens=total_tok,
        tokens_per_sec=tps,
        has_tool_call=bool(tool_calls_raw),
        tool_names=tool_names,
        response_preview=preview[:150],
    )


def print_header(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_result(r: BenchResult):
    status = "ERROR" if r.error else ("TOOL" if r.has_tool_call else "TEXT")
    print(f"  [{status:5s}] {r.scenario}")
    if r.error:
        print(f"         Error: {r.error}")
        return
    print(f"         Latency: {r.latency_ms:8.0f} ms")
    print(f"         Tokens:  {r.prompt_tokens} prompt + {r.completion_tokens} completion = {r.total_tokens} total")
    print(f"         Speed:   {r.tokens_per_sec:6.1f} tok/s")
    print(f"         Output:  {r.response_preview}")


def run_benchmark(url: str, model: str):
    print(f"\nHEMS LLM Benchmark")
    print(f"  Target:  {url}")
    print(f"  Model:   {model}")
    print(f"  GPU:     RX 9700 (gfx1201, RDNA4)")

    # ── Phase 0: Warmup ──
    print_header("Phase 0: Warmup (1 request)")
    r = call_llm(url, model, "テスト。", with_tools=False)
    r.scenario = "warmup"
    print_result(r)

    # ── Phase 1: Individual scenarios ──
    print_header("Phase 1: Scenario Tests (sequential)")
    results = []
    for name, sc in SCENARIOS.items():
        no_tools = sc.get("no_tools", False)
        r = call_llm(url, model, sc["user_msg"], with_tools=not no_tools)
        r.scenario = f"{name} — {sc['desc']}"
        print_result(r)
        results.append(r)

    # ── Phase 2: Sequential throughput (5 identical requests) ──
    print_header("Phase 2: Sequential Throughput (5x normal scenario)")
    seq_results = []
    for i in range(5):
        r = call_llm(url, model, SCENARIOS["normal"]["user_msg"])
        r.scenario = f"run {i+1}"
        seq_results.append(r)
        if r.error:
            print(f"  Run {i+1}: ERROR - {r.error}")
        else:
            print(f"  Run {i+1}: {r.latency_ms:7.0f} ms, {r.tokens_per_sec:5.1f} tok/s")

    valid = [r for r in seq_results if not r.error]
    if valid:
        avg_lat = sum(r.latency_ms for r in valid) / len(valid)
        avg_tps = sum(r.tokens_per_sec for r in valid) / len(valid)
        p50 = sorted(r.latency_ms for r in valid)[len(valid) // 2]
        print(f"  ── Avg: {avg_lat:.0f} ms | P50: {p50:.0f} ms | Avg speed: {avg_tps:.1f} tok/s")

    # ── Phase 3: Concurrent requests ──
    print_header("Phase 3: Concurrent Load (3 simultaneous requests)")
    scenarios_concurrent = [
        ("normal", SCENARIOS["normal"]["user_msg"]),
        ("high_temp", SCENARIOS["high_temp"]["user_msg"]),
        ("high_co2", SCENARIOS["high_co2"]["user_msg"]),
    ]

    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(call_llm, url, model, msg): label
            for label, msg in scenarios_concurrent
        }
        concurrent_results = []
        for fut in concurrent.futures.as_completed(futures):
            label = futures[fut]
            r = fut.result()
            r.scenario = label
            concurrent_results.append(r)
    wall_time = (time.perf_counter() - t0) * 1000

    for r in sorted(concurrent_results, key=lambda x: x.scenario):
        print_result(r)

    valid_c = [r for r in concurrent_results if not r.error]
    if valid_c:
        max_lat = max(r.latency_ms for r in valid_c)
        sum_tps = sum(r.tokens_per_sec for r in valid_c)
        print(f"  ── Wall time: {wall_time:.0f} ms | Max latency: {max_lat:.0f} ms | Agg speed: {sum_tps:.1f} tok/s")

    # ── Summary ──
    print_header("Summary")
    all_valid = [r for r in results if not r.error]
    if all_valid:
        tool_results = [r for r in all_valid if r.has_tool_call]
        text_results = [r for r in all_valid if not r.has_tool_call]

        if text_results:
            avg = sum(r.latency_ms for r in text_results) / len(text_results)
            tps = sum(r.tokens_per_sec for r in text_results) / len(text_results)
            print(f"  Text-only responses:  avg {avg:.0f} ms, {tps:.1f} tok/s ({len(text_results)} samples)")

        if tool_results:
            avg = sum(r.latency_ms for r in tool_results) / len(tool_results)
            tps = sum(r.tokens_per_sec for r in tool_results) / len(tool_results)
            names = set()
            for r in tool_results:
                names.update(r.tool_names)
            print(f"  Tool-call responses:  avg {avg:.0f} ms, {tps:.1f} tok/s ({len(tool_results)} samples)")
            print(f"  Tools invoked:        {', '.join(sorted(names))}")

    all_results = results + seq_results + concurrent_results
    errors = [r for r in all_results if r.error]
    if errors:
        print(f"  Errors: {len(errors)} failures")
        for r in errors:
            print(f"    - {r.scenario}: {r.error}")
    else:
        print(f"  Errors: 0")

    print(f"\n  Total requests: {len(all_results)}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HEMS LLM Benchmark")
    parser.add_argument("--url", default="http://localhost:11434/v1", help="Ollama API URL")
    parser.add_argument("--model", default="qwen2.5:14b", help="Model name")
    args = parser.parse_args()

    run_benchmark(args.url, args.model)
