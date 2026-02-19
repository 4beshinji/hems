#!/usr/bin/env python3
"""
SOMS LLM Evaluation Report Generator
Reads JSONL results from eval_models.py and generates a Markdown comparison report.

Usage:
    python3 infra/eval/eval_report.py
    # -> infra/eval/results/REPORT.md
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
REPORT_PATH = os.path.join(RESULTS_DIR, "REPORT.md")

JST = timezone(timedelta(hours=9))

BRAIN_SCENARIOS = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09", "B10"]
VOICE_SCENARIOS = ["V01", "V02", "V03", "V04"]
ALL_SCENARIOS = BRAIN_SCENARIOS + VOICE_SCENARIOS

SCENARIO_LABELS = {
    "B01": "正常 (no-op)",
    "B02": "高温",
    "B03": "高CO2",
    "B04": "低湿度",
    "B05": "コーヒー切れ",
    "B06": "入室検知",
    "B07": "長時間座位",
    "B08": "センサー急変",
    "B09": "複合問題",
    "B10": "重複回避",
    "V01": "告知文",
    "V02": "緊急告知",
    "V03": "拒否セリフ",
    "V04": "感謝メッセージ",
}


# ── Data loading ──


def load_all_results() -> dict:
    """Load all JSONL results. Returns {model: [records]}."""
    results = defaultdict(list)
    if not os.path.isdir(RESULTS_DIR):
        return results

    for fname in sorted(os.listdir(RESULTS_DIR)):
        if not fname.endswith(".jsonl"):
            continue
        path = os.path.join(RESULTS_DIR, fname)
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    model = record.get("model", "unknown")
                    results[model].append(record)
                except json.JSONDecodeError:
                    continue
    return dict(results)


def group_by_scenario(records: list) -> dict:
    """Group records by scenario_id. Returns {scenario_id: [records]}."""
    groups = defaultdict(list)
    for r in records:
        groups[r["scenario_id"]].append(r)
    return dict(groups)


# ── Scoring helpers ──


def scenario_pass_rate(records: list) -> tuple[int, int]:
    """Count passing runs for a scenario's records.
    A run passes if all bool scores are True."""
    passes = 0
    total = 0
    for r in records:
        scores = r.get("auto_scores", {})
        bools = [v for v in scores.values() if isinstance(v, bool)]
        if not bools:
            continue
        total += 1
        if all(bools):
            passes += 1
    return passes, total


def accuracy_score(by_scenario: dict, scenario_list: list) -> float:
    """Average pass rate across scenarios."""
    rates = []
    for sid in scenario_list:
        recs = by_scenario.get(sid, [])
        p, t = scenario_pass_rate(recs)
        if t > 0:
            rates.append(p / t)
    return sum(rates) / len(rates) if rates else 0.0


def bigram_set(text: str) -> set:
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


def consistency_for_scenario(records: list) -> float:
    """Consistency score for a single scenario's runs."""
    if len(records) < 2:
        return 1.0

    # Tool agreement
    tool_sets = []
    for r in records:
        parsed = r.get("parsed", {})
        names = tuple(sorted(
            tc["function"]["name"]
            for tc in parsed.get("tool_calls", [])
        ))
        tool_sets.append(names)
    tool_agree = 1.0 if len(set(tool_sets)) == 1 else 0.0

    # Finish reason agreement
    reasons = [r.get("parsed", {}).get("finish_reason", "") for r in records]
    finish_agree = 1.0 if len(set(reasons)) == 1 else 0.0

    # Text similarity
    texts = []
    for r in records:
        parsed = r.get("parsed", {})
        text = parsed.get("content", "") or ""
        for tc in parsed.get("tool_calls", []):
            args = tc["function"]["arguments"]
            if isinstance(args, dict):
                text += " " + " ".join(str(v) for v in args.values())
        texts.append(text)

    bi_sets = [bigram_set(t) for t in texts]
    sims = []
    for i in range(len(bi_sets)):
        for j in range(i + 1, len(bi_sets)):
            sims.append(jaccard(bi_sets[i], bi_sets[j]))
    text_sim = sum(sims) / len(sims) if sims else 1.0

    return 0.4 * tool_agree + 0.2 * finish_agree + 0.4 * text_sim


def avg_consistency(by_scenario: dict, scenario_list: list) -> float:
    """Average consistency across scenarios."""
    scores = []
    for sid in scenario_list:
        recs = by_scenario.get(sid, [])
        if recs:
            scores.append(consistency_for_scenario(recs))
    return sum(scores) / len(scores) if scores else 0.0


def latency_score(avg_ms: float) -> float:
    """Map latency to 0.0-1.0 score. 2s=1.0, 5s=0.5, 10s+=0.0."""
    if avg_ms <= 2000:
        return 1.0
    if avg_ms >= 10000:
        return 0.0
    return 1.0 - (avg_ms - 2000) / 8000


def avg_latency(records: list) -> float:
    """Average latency in ms across all records."""
    vals = [r["latency_ms"] for r in records if r.get("latency_ms")]
    return sum(vals) / len(vals) if vals else 0.0


def avg_tokens_per_sec(records: list) -> float:
    """Average tokens/sec."""
    vals = [r["tokens_per_sec"] for r in records if r.get("tokens_per_sec", 0) > 0]
    return sum(vals) / len(vals) if vals else 0.0


def text_quality_score(by_scenario: dict) -> float:
    """Voice scenario text quality: Japanese detection + length compliance."""
    checks = []
    for sid in VOICE_SCENARIOS:
        for r in by_scenario.get(sid, []):
            scores = r.get("auto_scores", {})
            if "is_japanese" in scores:
                checks.append(1.0 if scores["is_japanese"] else 0.0)
            if "length_ok" in scores:
                checks.append(1.0 if scores["length_ok"] else 0.0)
    return sum(checks) / len(checks) if checks else 0.0


def composite_score(accuracy: float, consistency: float, lat_score: float, text_qual: float) -> float:
    """Weighted composite: 0.35 accuracy + 0.25 consistency + 0.20 latency + 0.20 text quality."""
    return 0.35 * accuracy + 0.25 * consistency + 0.20 * lat_score + 0.20 * text_qual


# ── Report generation ──


def generate_report(all_results: dict) -> str:
    """Generate full Markdown report."""
    lines = []
    w = lines.append

    w("# SOMS LLM Model Evaluation Report")
    w("")
    w(f"Generated: {datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')} JST")
    w("")

    if not all_results:
        w("**No results found.** Run `python3 infra/eval/eval_models.py` first.")
        return "\n".join(lines)

    # Build per-model summaries
    model_stats = {}
    models_sorted = []

    for model, records in all_results.items():
        by_sc = group_by_scenario(records)

        brain_acc = accuracy_score(by_sc, BRAIN_SCENARIOS)
        voice_acc = accuracy_score(by_sc, VOICE_SCENARIOS)
        all_acc = accuracy_score(by_sc, ALL_SCENARIOS)

        con = avg_consistency(by_sc, ALL_SCENARIOS)
        lat = avg_latency(records)
        tps = avg_tokens_per_sec(records)
        lat_sc = latency_score(lat)
        txt_q = text_quality_score(by_sc)
        comp = composite_score(all_acc, con, lat_sc, txt_q)

        brain_pass = 0
        brain_total = 0
        for sid in BRAIN_SCENARIOS:
            p, t = scenario_pass_rate(by_sc.get(sid, []))
            if t > 0:
                brain_pass += 1 if p == t else 0
                brain_total += 1

        voice_pass = 0
        voice_total = 0
        for sid in VOICE_SCENARIOS:
            p, t = scenario_pass_rate(by_sc.get(sid, []))
            if t > 0:
                voice_pass += 1 if p == t else 0
                voice_total += 1

        model_stats[model] = {
            "by_scenario": by_sc,
            "records": records,
            "accuracy": all_acc,
            "consistency": con,
            "latency_ms": lat,
            "tokens_per_sec": tps,
            "latency_score": lat_sc,
            "text_quality": txt_q,
            "composite": comp,
            "brain_pass": brain_pass,
            "brain_total": brain_total,
            "voice_pass": voice_pass,
            "voice_total": voice_total,
        }
        models_sorted.append((comp, model))

    # Sort by composite score descending
    models_sorted.sort(key=lambda x: -x[0])
    model_order = [m for _, m in models_sorted]

    # ── Summary table ──
    w("## Model Comparison Summary")
    w("")
    w("| # | Model | Composite | Accuracy | Consistency | Avg Latency | tok/s | Brain | Voice |")
    w("|---|-------|-----------|----------|-------------|-------------|-------|-------|-------|")

    for rank, model in enumerate(model_order, 1):
        s = model_stats[model]
        w(
            f"| {rank} | {model} "
            f"| **{s['composite']:.2f}** "
            f"| {s['accuracy']:.2f} "
            f"| {s['consistency']:.2f} "
            f"| {s['latency_ms']:.0f}ms "
            f"| {s['tokens_per_sec']:.1f} "
            f"| {s['brain_pass']}/{s['brain_total']} "
            f"| {s['voice_pass']}/{s['voice_total']} |"
        )

    w("")
    w("Composite = 0.35 x Accuracy + 0.25 x Consistency + 0.20 x Latency + 0.20 x Text Quality")
    w("")

    # ── Scenario heatmap ──
    w("## Scenario Results Heatmap")
    w("")

    header = "| Scenario |"
    sep = "|----------|"
    for model in model_order:
        short = model.split(":")[0] if ":" in model else model
        header += f" {short} |"
        sep += "------|"
    w(header)
    w(sep)

    for sid in ALL_SCENARIOS:
        label = SCENARIO_LABELS.get(sid, sid)
        row = f"| {sid} {label} |"
        for model in model_order:
            by_sc = model_stats[model]["by_scenario"]
            recs = by_sc.get(sid, [])
            if not recs:
                row += " - |"
                continue

            marks = []
            for r in recs:
                scores = r.get("auto_scores", {})
                bools = [v for v in scores.values() if isinstance(v, bool)]
                if not bools:
                    marks.append("?")
                elif all(bools):
                    marks.append("o")
                else:
                    marks.append("x")

            all_pass = all(m == "o" for m in marks)
            status = "PASS" if all_pass else "FAIL"
            detail = "".join(marks)
            row += f" {status} {detail} |"
        w(row)

    w("")

    # ── Per-model details ──
    w("## Per-Model Details")
    w("")

    for model in model_order:
        s = model_stats[model]
        by_sc = s["by_scenario"]

        w(f"### {model}")
        w("")
        w(f"- **Composite Score**: {s['composite']:.3f}")
        w(f"- **Accuracy**: {s['accuracy']:.3f}")
        w(f"- **Consistency**: {s['consistency']:.3f}")
        w(f"- **Avg Latency**: {s['latency_ms']:.0f}ms (score: {s['latency_score']:.2f})")
        w(f"- **Avg tok/s**: {s['tokens_per_sec']:.1f}")
        w(f"- **Text Quality**: {s['text_quality']:.3f}")
        w(f"- **Brain**: {s['brain_pass']}/{s['brain_total']} scenarios all-pass")
        w(f"- **Voice**: {s['voice_pass']}/{s['voice_total']} scenarios all-pass")
        w(f"- **Total records**: {len(s['records'])}")
        w("")

        # Score breakdown per scenario
        w("#### Score Breakdown")
        w("")
        w("| Scenario | Pass | Consistency | Avg Latency | Scores |")
        w("|----------|------|-------------|-------------|--------|")

        for sid in ALL_SCENARIOS:
            recs = by_sc.get(sid, [])
            if not recs:
                continue

            p, t = scenario_pass_rate(recs)
            con = consistency_for_scenario(recs)
            lat = avg_latency(recs)

            # Collect all score keys
            all_score_keys = set()
            for r in recs:
                all_score_keys.update(r.get("auto_scores", {}).keys())
            all_score_keys.discard("api_success")

            score_details = []
            for key in sorted(all_score_keys):
                vals = []
                for r in recs:
                    v = r.get("auto_scores", {}).get(key)
                    if isinstance(v, bool):
                        vals.append(v)
                passes = sum(1 for v in vals if v)
                total_k = len(vals)
                if total_k > 0:
                    score_details.append(f"{key}:{passes}/{total_k}")

            w(
                f"| {sid} {SCENARIO_LABELS.get(sid, '')} "
                f"| {p}/{t} "
                f"| {con:.2f} "
                f"| {lat:.0f}ms "
                f"| {', '.join(score_details)} |"
            )

        w("")

        # Sample outputs
        w("#### Sample Outputs")
        w("")

        for sid in ALL_SCENARIOS:
            recs = by_sc.get(sid, [])
            if not recs:
                continue

            w(f"**{sid} {SCENARIO_LABELS.get(sid, '')}**")
            w("")

            for r in recs[:3]:
                parsed = r.get("parsed", {})
                run_num = r.get("run", "?")
                content = (parsed.get("content") or "").strip()
                tool_calls = parsed.get("tool_calls", [])
                lat = r.get("latency_ms", 0)

                w(f"- Run {run_num} ({lat:.0f}ms):")
                if tool_calls:
                    for tc in tool_calls:
                        name = tc["function"]["name"]
                        args = tc["function"]["arguments"]
                        args_str = json.dumps(args, ensure_ascii=False)
                        if len(args_str) > 120:
                            args_str = args_str[:120] + "..."
                        w(f"  - `{name}({args_str})`")
                if content:
                    preview = content[:200].replace("\n", " ")
                    w(f"  - Text: {preview}")
                if not tool_calls and not content:
                    w(f"  - (empty response)")
                w("")

        w("---")
        w("")

    # ── Latency distribution ──
    w("## Latency Distribution")
    w("")
    w("| Model | Min | P25 | Median | P75 | Max |")
    w("|-------|-----|-----|--------|-----|-----|")

    for model in model_order:
        recs = model_stats[model]["records"]
        lats = sorted(r["latency_ms"] for r in recs if r.get("latency_ms"))
        if not lats:
            continue
        n = len(lats)
        w(
            f"| {model} "
            f"| {lats[0]:.0f}ms "
            f"| {lats[n//4]:.0f}ms "
            f"| {lats[n//2]:.0f}ms "
            f"| {lats[3*n//4]:.0f}ms "
            f"| {lats[-1]:.0f}ms |"
        )

    w("")
    w("---")
    w(f"*Report generated by `infra/eval/eval_report.py`*")

    return "\n".join(lines)


def main():
    all_results = load_all_results()

    if not all_results:
        print(f"No results found in {RESULTS_DIR}/")
        print("Run 'python3 infra/eval/eval_models.py' first.")
        sys.exit(1)

    total_records = sum(len(recs) for recs in all_results.values())
    print(f"Loaded {total_records} records from {len(all_results)} models.")

    report = generate_report(all_results)

    with open(REPORT_PATH, "w") as f:
        f.write(report)

    print(f"Report written to: {REPORT_PATH}")
    print()

    # Print summary to stdout
    for line in report.split("\n"):
        if line.startswith("| ") and ("Composite" in line or "Model" in line or line.startswith("| #") or any(
            line.strip().startswith(f"| {i} ") for i in range(1, 20)
        )):
            print(line)
        elif line.startswith("|---"):
            print(line)


if __name__ == "__main__":
    main()
