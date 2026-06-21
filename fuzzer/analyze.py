#!/usr/bin/env python3
"""
Analyze the fuzzer crash log and produce a prioritised report.

Usage:
    python3 analyze.py [crash_log] [--out report.txt]
"""
import argparse
import collections
import json
import os
import sys
import textwrap
import time


def load_log(path: str) -> list[dict]:
    entries = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"WARNING: line {lineno} is malformed: {e}", file=sys.stderr)
    return entries


def _backtrace_key(rec: dict) -> str:
    """Dedup key: first 5 non-empty backtrace frames."""
    bt = [f for f in rec.get("backtrace", []) if f][:5]
    return "|".join(bt) if bt else rec.get("message", "?")[:120]


def _priority(rec: dict) -> int:
    """Higher = more serious."""
    kind = rec.get("kind", "")
    if "AddressSanitizer" in kind:
        return 10
    if "ThreadSanitizer" in kind:
        return 8
    if "LeakSanitizer" in kind:
        return 5
    if "UndefinedBehavior" in kind:
        return 6
    if "ProcessCrash" in kind:
        return 9
    return 3


def analyze(log_path: str, out_path: str | None = None):
    if not os.path.exists(log_path):
        print(f"No crash log found at {log_path} — no crashes recorded.")
        return

    entries = load_log(log_path)
    if not entries:
        print("Log is empty — no crashes recorded.")
        return

    # Flatten all CrashRecord dicts
    all_records: list[dict] = []
    for entry in entries:
        for rec in entry.get("records", []):
            rec = dict(rec)
            rec["_action"] = entry.get("action", "")
            rec["_crash_id"] = entry.get("crash_id", 0)
            rec["_screenshot"] = entry.get("screenshot")
            all_records.append(rec)

    # Deduplicate by backtrace key
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for rec in all_records:
        k = _backtrace_key(rec)
        groups[k].append(rec)

    # Sort groups by priority (desc) then count (desc)
    sorted_groups = sorted(
        groups.items(),
        key=lambda kv: (_priority(kv[1][0]), len(kv[1])),
        reverse=True,
    )

    lines = []
    lines.append("=" * 72)
    lines.append("QElectroTech Fuzzer — Crash Analysis Report")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Log file:  {log_path}")
    lines.append(f"Total crash events: {len(entries)}")
    lines.append(f"Unique crash signatures: {len(groups)}")
    lines.append("=" * 72)
    lines.append("")

    for rank, (key, recs) in enumerate(sorted_groups, 1):
        rep = recs[0]
        prio = _priority(rep)
        prio_label = {10: "CRITICAL", 9: "CRITICAL", 8: "HIGH",
                      6: "MEDIUM", 5: "MEDIUM"}.get(prio, "LOW")

        lines.append(f"[#{rank}] {prio_label}  kind={rep.get('kind','?')}  occurrences={len(recs)}")
        lines.append(f"  Message : {rep.get('message','?')[:100]}")
        lines.append(f"  First action  : {rep.get('_action','?')}")
        if rep.get("_screenshot"):
            lines.append(f"  Screenshot: {rep['_screenshot']}")

        bt = rep.get("backtrace", [])
        if bt:
            lines.append("  Backtrace (top 8):")
            for frame in bt[:8]:
                lines.append(f"    {frame}")

        # Show all triggering actions
        actions = sorted({r["_action"] for r in recs if r.get("_action")})
        if actions:
            lines.append("  Triggering actions: " + ", ".join(actions[:10]))

        lines.append("")

    report = "\n".join(lines)

    if out_path:
        with open(out_path, "w") as f:
            f.write(report)
        print(f"Report written to: {out_path}")
    else:
        print(report)


def main():
    ap = argparse.ArgumentParser(description="Analyze QET fuzzer crash log")
    ap.add_argument("log", nargs="?", default="/fuzzer/logs/crashes.jsonl",
                    help="Path to crashes.jsonl")
    ap.add_argument("--out", default=None, help="Write report to file")
    args = ap.parse_args()
    analyze(args.log, args.out)


if __name__ == "__main__":
    main()
