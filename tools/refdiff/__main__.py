#!/usr/bin/env python3
"""
tools.refdiff -- corpus-wide differential regression sweep (TOOLING-PLAN.md W3).

    python3 -m tools.refdiff --base master --head <ref> [--corpus DIR|FILE]

Builds each ref ONCE (via tools.abdiff.build, so a repeat run reuses the
per-sha build tree and ccache), then for every `.qet` project in the corpus
and every verb (`--resave`, `--info`, `--export-bom`, `--export-nets`,
`--export-links`) runs the command against both variants in isolated
simulator/env.py sandboxes, compares them with tools.abdiff.compare, and
classifies each difference as regression / improvement / change.

Only `regression` sets a non-zero exit code. A dated report (markdown + JSON)
is written under refdiff-reports/ by default.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import env
from tools.abdiff import build as buildmod
from tools.abdiff import compare as comparemod
from tools.abdiff import run as runmod
from tools.refdiff import classify as classifymod
from tools.refdiff import normalize as normalizemod
from tools.refdiff import report as reportmod

DEFAULT_REPO = Path("/home/user/qet-fix")
DEFAULT_CORPUS = DEFAULT_REPO / "examples"

# (verb flag, output filename written into the sandbox working dir, kind).
# `kind` is "resave" (canon-diffed) or "text" (normalised then byte-diffed).
VERBS = [
    ("--resave", "out.qet", "resave"),
    ("--info", "out.json", "text"),
    ("--export-bom", "out.csv", "text"),
    ("--export-nets", "out.json", "text"),
    ("--export-links", "out.csv", "text"),
]


def _log(msg: str) -> None:
    print(f"[refdiff] {msg}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python3 -m tools.refdiff",
        description="Sweep a corpus of .qet projects through two QET builds and "
                    "classify each difference as regression / improvement / change.",
    )
    ap.add_argument("--base", required=True, metavar="REF", help="baseline ref (resolved in --repo)")
    ap.add_argument("--head", required=True, metavar="REF", help="head ref under test")
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS,
                    help="directory of .qet projects, or a single .qet (default %(default)s)")
    ap.add_argument("--repo", type=Path, default=DEFAULT_REPO, help="QET source checkout")
    ap.add_argument("--build-root", type=Path, default=None,
                    help="per-variant build trees (default <repo>/build-ab)")
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="per-variant run timeout in seconds (default 120)")
    ap.add_argument("--out", type=Path, default=None,
                    help="report dir (default refdiff-reports/<timestamp> under the repo root)")
    ap.add_argument("--limit", type=int, default=0,
                    help="only sweep the first N projects (0 = all; a testing aid)")
    ap.add_argument("--keep", action="store_true", help="keep each variant's produced-files scratch dir")
    return ap


def _projects(corpus: Path) -> list[Path]:
    if corpus.is_file():
        return [corpus]
    return sorted(corpus.glob("*.qet"))


def _normalize_produced(verb: str, kind: str, produced_dir: Path, out_name: str) -> None:
    if kind != "text":
        return
    p = produced_dir / out_name
    if not p.exists():
        return
    try:
        normalizemod.normalize_export(verb, p)
    except Exception:
        # Leave the raw file alone; compare() will surface whatever the
        # difference is (missing/malformed/byte-diff) in its own reasons.
        pass


# This host is shared between sessions: a concurrent session can have a
# qelectrotech process alive at any moment, and env.assert_no_other_qet_running()
# (correctly) refuses to run while one is (SingleApplication would forward to
# it and every result would silently describe the wrong binary). Rather than
# abort the whole sweep -- the first real W3 run died at comparison 81 of 115
# exactly this way -- wait for the transient process to exit and retry.
_SANDBOX_RETRY_ATTEMPTS = 12
_SANDBOX_RETRY_WAIT = 10.0  # seconds


def _run_variant_retry(binary, command, *, timeout, produced_dir):
    last = None
    for attempt in range(_SANDBOX_RETRY_ATTEMPTS):
        try:
            return runmod.run_variant(binary, command, timeout=timeout, produced_dir=produced_dir)
        except env.SandboxError as e:
            last = e
            if attempt < _SANDBOX_RETRY_ATTEMPTS - 1:
                _log(f"concurrent qelectrotech detected ({e}); "
                     f"waiting {_SANDBOX_RETRY_WAIT:.0f}s (attempt {attempt + 1}/{_SANDBOX_RETRY_ATTEMPTS})")
                time.sleep(_SANDBOX_RETRY_WAIT)
    assert last is not None
    raise last


def _skipped_finding(project: str, verb: str, reason: str) -> dict:
    return {
        "project": project,
        "verb": verb,
        "category": "skipped",
        "verdict": "skipped",
        "reasons": [reason],
        "lost_elements": [], "gained_elements": [],
        "lost_uuids": [], "gained_uuids": [],
        "lost_conductors": 0, "gained_conductors": 0,
        "base": {"returncode": None, "crashed": False, "crash_kind": None,
                 "crash_message": None, "timed_out": False, "wall_seconds": 0.0},
        "head": {"returncode": None, "crashed": False, "crash_kind": None,
                 "crash_message": None, "timed_out": False, "wall_seconds": 0.0},
    }


def _run_summary(outcome) -> dict:
    return {
        "returncode": outcome.returncode,
        "crashed": outcome.crashed,
        "crash_kind": outcome.crash_kind,
        "crash_message": outcome.crash_message,
        "timed_out": outcome.timed_out,
        "wall_seconds": round(outcome.wall_seconds, 2),
    }


def _build_summary(build: buildmod.BuildResult) -> dict:
    return {
        "ref": build.ref,
        "sha": build.sha,
        "configure_seconds": round(build.configure_seconds, 2),
        "build_seconds": round(build.build_seconds, 2),
        "reused": build.reused,
    }


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    env.assert_no_other_qet_running("qelectrotech")

    build_root = args.build_root or (args.repo / "build-ab")

    _log(f"building base ({args.base}) ...")
    build_base = buildmod.build_variant(args.repo, args.base, build_root)
    _log(f"base built in {build_base.configure_seconds + build_base.build_seconds:.1f}s -> {build_base.binary}"
         + (" [reused]" if build_base.reused else ""))

    _log(f"building head ({args.head}) ...")
    build_head = buildmod.build_variant(args.repo, args.head, build_root)
    _log(f"head built in {build_head.configure_seconds + build_head.build_seconds:.1f}s -> {build_head.binary}"
         + (" [reused]" if build_head.reused else ""))

    projects = _projects(args.corpus)
    if not projects:
        build_parser().error(f"no .qet projects under {args.corpus}")
    if args.limit:
        projects = projects[: args.limit]
    _log(f"corpus: {len(projects)} project(s), {len(VERBS)} verb(s) -> {len(projects) * len(VERBS)} comparisons")

    scratch = Path(tempfile.mkdtemp(prefix="refdiff-"))
    findings: list[dict] = []
    counts = {"same": 0, "regression": 0, "improvement": 0, "change": 0, "skipped": 0}

    try:
        for idx, project in enumerate(projects, 1):
            stem = project.stem
            for verb, out_name, kind in VERBS:
                command = [verb, str(project), out_name]
                produced_a = scratch / "a" / str(idx) / verb.lstrip("-")
                produced_b = scratch / "b" / str(idx) / verb.lstrip("-")

                try:
                    outcome_a = _run_variant_retry(build_base.binary, command, timeout=args.timeout, produced_dir=produced_a)
                    outcome_b = _run_variant_retry(build_head.binary, command, timeout=args.timeout, produced_dir=produced_b)
                except env.SandboxError as e:
                    # Shared host: another session's qelectrotech never exited
                    # within the retry window. Record and move on rather than
                    # aborting the whole sweep (a skipped comparison cannot
                    # count as a regression).
                    counts["skipped"] += 1
                    findings.append(_skipped_finding(stem, verb, str(e)))
                    _log(f"{stem} {verb}: SKIPPED ({e})")
                    continue

                _normalize_produced(verb, kind, produced_a, out_name)
                _normalize_produced(verb, kind, produced_b, out_name)

                comparison = comparemod.compare(command, outcome_a, outcome_b, produced_a, produced_b)
                delta = (classifymod.resave_delta(produced_a, produced_b, out_name)
                         if kind == "resave" else None)
                category, reasons = classifymod.classify(comparison, delta)

                counts[category] += 1
                finding = {
                    "project": stem,
                    "verb": verb,
                    "category": category,
                    "verdict": comparison.verdict,
                    "reasons": reasons,
                    "lost_elements": delta.lost_elements if delta else [],
                    "gained_elements": delta.gained_elements if delta else [],
                    "lost_uuids": delta.lost_uuids if delta else [],
                    "gained_uuids": delta.gained_uuids if delta else [],
                    "lost_conductors": len(delta.lost_conductors) if delta else 0,
                    "gained_conductors": len(delta.gained_conductors) if delta else 0,
                    "base": _run_summary(outcome_a),
                    "head": _run_summary(outcome_b),
                }
                findings.append(finding)
                if category != classifymod.CATEGORY_SAME:
                    _log(f"{stem} {verb}: {category.upper()} ({comparison.verdict})")
    finally:
        if args.keep:
            _log(f"kept produced-files scratch dir: {scratch}")
        else:
            shutil.rmtree(scratch, ignore_errors=True)

    regressions = [f for f in findings if f["category"] == classifymod.CATEGORY_REGRESSION]
    non_same = [f for f in findings if f["category"] != classifymod.CATEGORY_SAME]

    if args.out:
        out_dir = args.out
    else:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        out_dir = Path(__file__).resolve().parents[2] / "refdiff-reports" / stamp

    sweep = {
        "base_ref": args.base,
        "base_sha": build_base.sha,
        "head_ref": args.head,
        "head_sha": build_head.sha,
        "corpus": str(args.corpus),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timeout": args.timeout,
        "verbs": [v for v, _, _ in VERBS],
        "build": {"base": _build_summary(build_base), "head": _build_summary(build_head)},
        "summary": {
            "projects": len(projects),
            "comparisons": len(findings),
            "same": counts["same"],
            "regression": counts["regression"],
            "improvement": counts["improvement"],
            "change": counts["change"],
            "skipped": counts["skipped"],
        },
        "regressions": regressions,
        "findings": non_same,
    }
    md, js = reportmod.write(sweep, out_dir)

    print(f"refdiff: {sweep['base_ref']} vs {sweep['head_ref']}")
    print(f"  {counts['same']} same, {counts['regression']} regression, "
          f"{counts['improvement']} improvement, {counts['change']} change "
          f"({len(findings)} comparisons)")
    print(f"  report: {md}")
    print(f"  json:   {js}")

    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
