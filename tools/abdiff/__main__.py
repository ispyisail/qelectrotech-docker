#!/usr/bin/env python3
"""
scripts/qet-ab.sh's implementation.

    python3 -m tools.abdiff --a REF --b REF [--patch FILE] -- <qelectrotech CLI args...>

Builds both variants (tools.abdiff.build), runs the given command against
each in its own simulator/env.py sandbox with its own --timeout
(tools.abdiff.run), and classifies the result (tools.abdiff.compare) as
same / differs / a-only-fails / b-only-fails. Exit code is 0 only for
`same`; every other verdict means a real difference was found.

Variant B's build runs after variant A's *and reuses the same globally
shared ccache* (CCACHE_DIR, see scripts/qet-fastbuild.sh), so on two refs
that share most of their source the second build is measurably faster
even though it lands in its own, brand-new build-ab/<sha>/ directory.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import env
from tools.abdiff import build as buildmod
from tools.abdiff import compare as comparemod
from tools.abdiff import report as reportmod
from tools.abdiff import run as runmod

DEFAULT_REPO = Path("/home/user/qet-fix")


def _split_command(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], argv[i + 1:]
    return argv, []


def _log(msg: str) -> None:
    print(f"[qet-ab] {msg}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="qet-ab.sh",
        description=(
            "Build two QET variants and diff the result of running the same "
            "command against each. Everything after a literal '--' is the "
            "command, passed unchanged to both variants' qelectrotech binary."
        ),
    )
    ap.add_argument("--a", required=True, metavar="REF", help="variant A: a ref resolvable in --repo")
    ap.add_argument("--b", required=True, metavar="REF", help="variant B")
    ap.add_argument("--patch", type=Path, default=None,
                     help="patch file applied to variant B's worktree before building")
    ap.add_argument("--repo", type=Path, default=DEFAULT_REPO, help="QET source checkout (default %(default)s)")
    ap.add_argument("--build-root", type=Path, default=None,
                     help="where per-variant build trees live (default <repo>/build-ab)")
    ap.add_argument("--timeout", type=float, default=60.0,
                     help="per-variant run timeout in seconds (default 60). "
                          "A run that exceeds this is classified as a failure, never as 'no result'.")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--keep", action="store_true",
                     help="keep the scratch dir holding each variant's produced files instead of deleting it")
    return ap


def main(argv: list[str]) -> int:
    harness_args, command = _split_command(argv)
    args = build_parser().parse_args(harness_args)

    if not command:
        build_parser().error("no command given -- pass the qelectrotech CLI args after '--'")

    build_root = args.build_root or (args.repo / "build-ab")

    # Global guard before touching anything: SingleApplication forwards to
    # a live instance with no error (TOOLING-PLAN.md trap #1). Run this
    # once up front, in addition to run.py's own per-variant check, so a
    # stray instance is caught before spending minutes on a build.
    env.assert_no_other_qet_running("qelectrotech")

    _log(f"building variant A ({args.a}) ...")
    build_a = buildmod.build_variant(args.repo, args.a, build_root)
    _log(f"variant A built in {build_a.configure_seconds + build_a.build_seconds:.1f}s -> {build_a.binary}"
         + (" [reused]" if build_a.reused else ""))

    _log(f"building variant B ({args.b}) ...")
    build_b = buildmod.build_variant(args.repo, args.b, build_root, patch=args.patch)
    _log(f"variant B built in {build_b.configure_seconds + build_b.build_seconds:.1f}s -> {build_b.binary}"
         + (" [reused]" if build_b.reused else ""))

    scratch = Path(tempfile.mkdtemp(prefix="qet-ab-run-"))
    produced_a, produced_b = scratch / "a", scratch / "b"
    try:
        _log(f"running variant A: {' '.join(command)} (timeout {args.timeout:.0f}s)")
        outcome_a = runmod.run_variant(build_a.binary, command, timeout=args.timeout, produced_dir=produced_a)
        _log(f"running variant B: {' '.join(command)} (timeout {args.timeout:.0f}s)")
        outcome_b = runmod.run_variant(build_b.binary, command, timeout=args.timeout, produced_dir=produced_b)

        comparison = comparemod.compare(command, outcome_a, outcome_b, produced_a, produced_b)
        data = reportmod.to_dict(command, build_a, build_b, outcome_a, outcome_b, comparison)

        if args.format == "json":
            print(json.dumps(data, indent=2))
        else:
            print(reportmod.to_text(data))
    finally:
        if args.keep:
            _log(f"kept produced-files scratch dir: {scratch}")
        else:
            shutil.rmtree(scratch, ignore_errors=True)

    return 0 if comparison.verdict == comparemod.VERDICT_SAME else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
