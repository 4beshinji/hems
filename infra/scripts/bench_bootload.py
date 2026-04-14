#!/usr/bin/env python3
"""
Boot Load Benchmark — compare LLM models on HEMS batch tasks.

Tests the 3 tasks that boot_load_manager + event_automation run at wake_up:
  1. morning_briefing  (boot_load_manager._generate_briefing)
  2. morning_greeting  (event_automation._action_morning_greeting)
  3. task_planning     (event_automation._action_task_planning)

Usage:
  python bench_bootload.py --models gemma4:26b-a4b-it-q4_K_M gemma4:31b-it-q4_K_M
  python bench_bootload.py --models gemma4:26b-a4b-it-q4_K_M gemma4:31b-it-q4_K_M --runs 3
  python bench_bootload.py --url http://localhost:11444  # custom Ollama URL
"""
import argparse
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

# ── Mock data (mirrors real HEMS world model state) ────────────────────────
MOCK_CONTEXT = {
    "time": "06:45",
    "weather": {"condition": "晴れ", "temperature": 18, "humidity": 55},
    "sleep": {"duration_minutes": 430, "quality_score": 78},
    "schedule": [
        "- 09:00 週次ミーティング",
        "- 12:00 ランチ",
        "- 15:00 コードレビュー",
        "- 19:00 ジム",
    ],
    "news_chunks": [
        "日銀が政策金利を0.5%に据え置くことを決定した。",
        "東京都内で震度3の地震が発生。津波の心配はなし。",
        "AIスタートアップへの国内投資が前年比2倍に増加した。",
        "桜の開花が全国的に1週間早まる見通し。",
        "国内電力需要、今夏も逼迫の恐れ。節電要請の可能性。",
    ],
    "tasks": [
        {"id": 1, "title": "週次レポート作成", "description": "今週の進捗をまとめてSlackに投稿"},
        {"id": 2, "title": "サーバー監視設定", "description": "Grafanaダッシュボードにアラートを追加"},
        {"id": 3, "title": "読書", "description": "「Clean Architecture」第15章まで"},
    ],
}

# ── Prompt templates (exact copies from HEMS source) ───────────────────────

def build_morning_briefing_prompt(ctx: dict) -> tuple[str, str]:
    """boot_load_manager._generate_briefing"""
    context_parts = [f"現在時刻: {ctx['time']}"]
    w = ctx["weather"]
    context_parts.append(f"天気: {w['condition']}")
    context_parts.append(f"気温: {w['temperature']}°C")
    s = ctx["sleep"]
    context_parts.append(f"昨夜の睡眠: {s['duration_minutes']}分 (品質 {s['quality_score']}/100)")
    context_parts.append("今日の予定:\n" + "\n".join(ctx["schedule"]))
    context_parts.append("ニュース概要:\n" + "\n".join(ctx["news_chunks"][:5]))
    context = "\n".join(context_parts)
    prompt = (
        "以下の情報を元に、自然な朝のブリーフィングを生成してください。\n"
        "・起床の挨拶から始め、天気→今日の予定→ニュース→締めの言葉の順で\n"
        "・合計200〜300文字程度、口語体で\n"
        "・テキストのみ出力（説明や括弧書きなし）\n\n"
        f"{context}"
    )
    system = "あなたは家庭環境AIアシスタントです。簡潔で自然な日本語で話してください。"
    return system, prompt


def build_morning_greeting_prompt(ctx: dict) -> tuple[str, str]:
    """event_automation._action_morning_greeting"""
    w = ctx["weather"]
    s = ctx["sleep"]
    context = "\n".join([
        f"時刻: {ctx['time']}",
        f"天気: {w['condition']}",
        f"外気温: {w['temperature']}°C",
        f"昨夜の睡眠: {s['duration_minutes']}分 (品質{s['quality_score']}/100)",
    ])
    prompt = (
        "以下の状況に基づいて朝の挨拶を1文（50文字以内）で生成してください。\n"
        "セリフのみ出力してください。\n\n"
        f"{context}"
    )
    system = "短い日本語の朝の挨拶を生成してください。"
    return system, prompt


def build_task_planning_prompt(ctx: dict) -> tuple[str, str]:
    """event_automation._action_task_planning"""
    tasks_text = "\n".join(
        f"- [{t['id']}] {t['title']}: {t.get('description', '')}"
        for t in ctx["tasks"]
    )
    prompt = (
        f"以下のアクティブタスクについて、各タスクの詳細な実行手順・目安時間・注意点を"
        f"日本語で簡潔にまとめてください。発話用なので200文字以内でお願いします。\n\n{tasks_text}"
    )
    system = "あなたはタスク管理アシスタントです。簡潔に答えてください。"
    return system, prompt


TASKS = {
    "morning_briefing": (build_morning_briefing_prompt, 400),
    "morning_greeting": (build_morning_greeting_prompt, 100),
    "task_planning":    (build_task_planning_prompt,    300),
}

# ── Ollama API ──────────────────────────────────────────────────────────────

def ollama_chat(
    base_url: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    think: bool = False,
) -> tuple[str, float, int]:
    """Returns (content, elapsed_sec, total_tokens). Raises on error."""
    url = f"{base_url}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "think": think,
        "options": {"num_predict": max_tokens},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read())
    elapsed = time.perf_counter() - t0

    msg = body.get("message", {})
    content = msg.get("content", "") or ""
    thinking = msg.get("thinking", "") or ""
    total_tokens = body.get("eval_count", 0) + body.get("prompt_eval_count", 0)
    eval_tokens = body.get("eval_count", 0)
    eval_duration = body.get("eval_duration", 0)  # nanoseconds
    tps = eval_tokens / (eval_duration / 1e9) if eval_duration > 0 else 0.0
    return content, elapsed, total_tokens, tps, thinking


# ── Benchmark runner ────────────────────────────────────────────────────────

@dataclass
class RunResult:
    content: str
    elapsed: float
    total_tokens: int
    tps: float


@dataclass
class TaskResult:
    task_name: str
    model: str
    runs: list[RunResult] = field(default_factory=list)

    @property
    def avg_elapsed(self) -> float:
        return sum(r.elapsed for r in self.runs) / len(self.runs)

    @property
    def avg_tps(self) -> float:
        return sum(r.tps for r in self.runs) / len(self.runs)

    @property
    def avg_tokens(self) -> float:
        return sum(r.total_tokens for r in self.runs) / len(self.runs)


def run_benchmark(
    base_url: str,
    models: list[str],
    task_names: list[str],
    num_runs: int,
    ctx: dict,
    think: bool = False,
) -> dict[str, dict[str, TaskResult]]:
    """results[model][task] = TaskResult"""
    results: dict[str, dict[str, TaskResult]] = {m: {} for m in models}

    for model in models:
        print(f"\n{'='*60}")
        print(f"  Model: {model}")
        print(f"{'='*60}")

        # Warm-up: short ping to load model into VRAM
        print("  [warm-up] loading model...", end="", flush=True)
        try:
            ollama_chat(base_url, model, "テスト", "テスト", 5)
            print(" done")
        except Exception as e:
            print(f" FAILED: {e}")
            continue

        for task_name in task_names:
            build_fn, base_max_tokens = TASKS[task_name]
            # thinking consumes tokens too — give 4× budget when enabled
            max_tokens = base_max_tokens * 4 if think else base_max_tokens
            system, user = build_fn(ctx)
            tr = TaskResult(task_name=task_name, model=model)
            print(f"\n  ── {task_name} (×{num_runs}) ──")

            for i in range(num_runs):
                print(f"    run {i+1}/{num_runs}...", end="", flush=True)
                try:
                    content, elapsed, total_tokens, tps, thinking = ollama_chat(
                        base_url, model, system, user, max_tokens, think=think
                    )
                    tr.runs.append(RunResult(content, elapsed, total_tokens, tps))
                    think_info = f"  thinking={len(thinking)}chars" if thinking else ""
                    print(f" {elapsed:.1f}s  {tps:.1f} tok/s  {len(content)}chars{think_info}")
                except Exception as e:
                    print(f" ERROR: {e}")

            if tr.runs:
                results[model][task_name] = tr
                # Show last response for quality check
                last = tr.runs[-1].content
                print(f"    ↳ 出力例: {last[:120].replace(chr(10),' ')!r}")

    return results


def print_summary(results: dict, models: list[str], task_names: list[str]):
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")

    col_w = 22
    header = f"{'Task':<20}" + "".join(f"{m[:col_w]:>{col_w}}" for m in models)
    print(header)
    print("-" * len(header))

    for task_name in task_names:
        # Speed row
        row = f"{task_name+' [s]':<20}"
        for m in models:
            tr = results[m].get(task_name)
            row += f"{tr.avg_elapsed:>{col_w}.1f}" if tr else f"{'N/A':>{col_w}}"
        print(row)

        # tok/s row
        row = f"{'  tok/s':<20}"
        for m in models:
            tr = results[m].get(task_name)
            row += f"{tr.avg_tps:>{col_w}.1f}" if tr else f"{'N/A':>{col_w}}"
        print(row)

    print()
    print("(品質はログの「出力例」を目視確認してください)")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HEMS Boot Load Benchmark")
    parser.add_argument(
        "--models", nargs="+",
        default=["gemma4:26b-a4b-it-q4_K_M", "gemma4:31b-it-q4_K_M"],
        help="Ollama model names to compare",
    )
    parser.add_argument("--think", action="store_true", help="Enable thinking mode")
    parser.add_argument("--runs", type=int, default=2, help="Runs per task (default: 2)")
    parser.add_argument(
        "--tasks", nargs="+",
        default=["morning_briefing", "morning_greeting", "task_planning"],
        help="Tasks to benchmark",
    )
    parser.add_argument(
        "--url", default="http://localhost:11444",
        help="Ollama base URL (default: http://localhost:11444)",
    )
    args = parser.parse_args()

    print("HEMS Boot Load Benchmark")
    print(f"  Models : {args.models}")
    print(f"  Tasks  : {args.tasks}")
    print(f"  Runs   : {args.runs} per task")
    print(f"  Think  : {args.think}")
    print(f"  Ollama : {args.url}")

    results = run_benchmark(args.url, args.models, args.tasks, args.runs, MOCK_CONTEXT,
                            think=args.think)
    print_summary(results, args.models, args.tasks)


if __name__ == "__main__":
    main()
