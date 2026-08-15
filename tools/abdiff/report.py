"""Text and JSON rendering of one A/B comparison."""
from __future__ import annotations

from tools.abdiff.build import BuildResult
from tools.abdiff.compare import Comparison
from simulator.proc import Outcome


def _build_summary(build: BuildResult, outcome: Outcome) -> dict:
    return {
        "ref": build.ref,
        "sha": build.sha,
        "patch": str(build.patch) if build.patch else None,
        "configure_seconds": round(build.configure_seconds, 2),
        "build_seconds": round(build.build_seconds, 2),
        "total_build_seconds": round(build.configure_seconds + build.build_seconds, 2),
        "build_reused": build.reused,
        "returncode": outcome.returncode,
        "timed_out": outcome.timed_out,
        "crashed": outcome.crashed,
        "crash_kind": outcome.crash_kind,
        "crash_message": outcome.crash_message,
        "run_wall_seconds": round(outcome.wall_seconds, 2),
    }


def to_dict(
    command: list[str],
    build_a: BuildResult,
    build_b: BuildResult,
    outcome_a: Outcome,
    outcome_b: Outcome,
    comparison: Comparison,
) -> dict:
    return {
        "command": command,
        "variant_a": _build_summary(build_a, outcome_a),
        "variant_b": _build_summary(build_b, outcome_b),
        "verdict": comparison.verdict,
        "reasons": comparison.reasons,
    }


def _run_status(v: dict) -> str:
    if v["timed_out"]:
        return "TIMEOUT"
    if v["crashed"]:
        return f"CRASH ({v['crash_kind']}: {v['crash_message']})"
    return f"exit {v['returncode']}"


def to_text(data: dict) -> str:
    lines = [f"command: {' '.join(data['command'])}", ""]
    for label in ("variant_a", "variant_b"):
        v = data[label]
        reused = " [reused]" if v["build_reused"] else ""
        lines.append(
            f"[{label}] ref={v['ref']} sha={v['sha'][:12]} "
            f"build={v['total_build_seconds']:.1f}s "
            f"(configure {v['configure_seconds']:.1f}s + build {v['build_seconds']:.1f}s){reused}"
        )
        lines.append(f"          run: {_run_status(v)} ({v['run_wall_seconds']:.1f}s wall)")
    lines.append("")
    lines.append(f"verdict: {data['verdict'].upper()}")
    if data["reasons"]:
        lines.append("reasons:")
        for r in data["reasons"]:
            for sub in r.splitlines():
                lines.append(f"  {sub}")
    return "\n".join(lines)
