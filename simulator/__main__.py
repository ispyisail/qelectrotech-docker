#!/usr/bin/env python3
"""
Simulator CLI entry point.

    python3 -m simulator sweep   --binary PATH [--corpus DIR] [--iterations N] ...
    python3 -m simulator replay  --binary PATH --trace FILE.json
    python3 -m simulator selftest             # runs the unit test suite, no binary needed
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulator import env, mutate
from simulator.runner import RunConfig, run_sweep, _apply_trace_to_bytes, _execute_and_check
from simulator.trace import Trace

DEFAULT_CORPUS = Path("/home/user/qet-fix/examples")
DEFAULT_REPORTS = Path(__file__).resolve().parent / "reports"


def cmd_sweep(args: argparse.Namespace) -> int:
    cfg = RunConfig(
        binary=args.binary,
        corpus_dir=args.corpus,
        reports_dir=args.reports,
        iterations=args.iterations,
        chain_length=args.chain_length,
        grid=args.grid,
        timeout=args.timeout,
        master_seed=args.seed,
        mutator_names=args.mutators or list(mutate.ALL_MUTATOR_NAMES),
    )
    summary = run_sweep(cfg)
    print(json.dumps(summary, indent=2))
    return 1 if summary["findings_by_oracle"] else 0


def cmd_replay(args: argparse.Namespace) -> int:
    trace = Trace.load(args.trace)
    seed_path = args.corpus / trace.seed_name
    if not seed_path.exists():
        print(f"seed file not found: {seed_path}", file=sys.stderr)
        return 2
    seed_bytes = seed_path.read_bytes()

    import hashlib
    actual_sha = hashlib.sha256(seed_bytes).hexdigest()
    if actual_sha != trace.seed_sha256:
        print(f"WARNING: seed file hash mismatch -- {seed_path} has changed since this "
              f"trace was recorded ({actual_sha} != {trace.seed_sha256})", file=sys.stderr)

    # Same SingleApplication guard as sweep and every fixture: replaying
    # against a live instance would silently report that instance's state
    # instead of ours (see env.py's module docstring for the two past
    # cross-contaminations).
    env.assert_no_other_qet_running(args.binary)

    try:
        mutated = _apply_trace_to_bytes(trace, seed_bytes)
    except mutate.ReplayError as e:
        print(f"cannot replay trace: {e}", file=sys.stderr)
        return 2
    cfg = RunConfig(binary=args.binary, corpus_dir=args.corpus, reports_dir=DEFAULT_REPORTS)

    with env.sandbox_context() as sb:
        findings = _execute_and_check(mutated, cfg, sb)

    if not findings:
        print("replay produced no findings (trace no longer reproduces).")
        return 0
    for f in findings:
        print(f"{f.oracle} ({f.severity}): {f.message}")
        print(f"  detail: {json.dumps(f.detail, indent=2)}")
    return 1


def cmd_selftest(args: argparse.Namespace) -> int:
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s",
         str(Path(__file__).resolve().parent / "tests"), "-v"],
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    return result.returncode


def main() -> int:
    ap = argparse.ArgumentParser(prog="python3 -m simulator")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("sweep", help="run a mutation stress sweep")
    sp.add_argument("--binary", required=True)
    sp.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    sp.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    sp.add_argument("--iterations", type=int, default=50)
    sp.add_argument("--chain-length", type=int, default=1)
    sp.add_argument("--grid", type=int, default=10)
    sp.add_argument("--timeout", type=float, default=20.0)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--mutators", nargs="*", default=None,
                     choices=mutate.ALL_MUTATOR_NAMES, metavar="MUTATOR")
    sp.set_defaults(func=cmd_sweep)

    rp = sub.add_parser("replay", help="replay a saved trace and show its findings")
    rp.add_argument("--binary", required=True)
    rp.add_argument("--trace", type=Path, required=True)
    rp.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    rp.set_defaults(func=cmd_replay)

    tp = sub.add_parser("selftest", help="run the simulator's own unit tests (no binary needed)")
    tp.set_defaults(func=cmd_selftest)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
