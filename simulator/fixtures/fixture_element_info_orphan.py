#!/usr/bin/env python3
"""
Fixture: delete an element then undo must not leave an element_info
orphan row (qelectrotech-source-mirror PR #664).

Unlike fixture_known_bugs.py, this needs a binary built from a branch
containing --test-ops (qet-fix branch feature/test-ops-cli) -- plain
--resave cannot drive this at all, since the bug is about live
delete+undo, and the project database it manifests in is
QSqlDatabase-backed :memory: SQLite that never touches disk (verified:
projectDataBase::createDataBase() calls .open() with no
setDatabaseName() call first). This fixture is the reason --test-ops
exists.

The check: after select -> delete -> undo on any element with a
resolvable uuid, `SELECT COUNT(*) FROM element` must equal
`SELECT COUNT(*) FROM element_info`. Before PR #664, removeElement()
never cleaned element_info, so the re-insert on undo hits a UNIQUE
constraint and silently fails (logged, not surfaced) -- verified by
hand this session: reproduces on qet-fix/examples/741.qet, stderr shows
`UNIQUE constraint failed: element_info.element_uuid`, and the same
sequence against the actual PR #664 fix branch produces no such error
and matching counts.

Usage:
    python3 -m simulator.fixtures.fixture_element_info_orphan --binary PATH
    python3 -m simulator.fixtures.fixture_element_info_orphan --binary PATH --expect-bug
        (use against a pre-#664 binary to confirm the fixture still
        reproduces the original bug)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import env
from simulator.executor_ops import first_element_uuid, run_ops

DEFAULT_CORPUS = Path("/home/user/qet-fix/examples")


def check_one(binary: str, seed: Path, sandbox: env.Sandbox, timeout: float) -> tuple[bool, str]:
    """Returns (is_orphaned, detail)."""
    uuid = first_element_uuid(seed)
    if uuid is None:
        return False, "no elements in this file -- nothing to delete, skipped"

    ops = [
        {"op": "select", "uuids": [uuid]},
        {"op": "delete"},
        {"op": "undo"},
    ]
    outcome, _, summary = run_ops(binary, seed, ops, sandbox, timeout=timeout)

    if outcome.crashed:
        return True, f"CRASHED applying delete+undo: {outcome.crash_kind}: {outcome.crash_message}"
    if summary is None:
        return True, (
            f"no JSON summary on stdout -- this binary may not have --test-ops "
            f"(feature/test-ops-cli): {outcome.stdout[-300:]!r}"
        )

    constraint_error = "UNIQUE constraint failed: element_info" in outcome.stderr
    count_mismatch = summary["element_count"] != summary["element_info_count"]

    if constraint_error or count_mismatch:
        return True, (
            f"element_count={summary['element_count']} "
            f"element_info_count={summary['element_info_count']} "
            f"constraint_error_in_stderr={constraint_error}"
        )
    return False, f"clean: {summary['element_count']} == {summary['element_info_count']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--expect-bug", action="store_true",
                     help="Invert the expectation: pass only if the orphan-row bug "
                          "reproduces (use against a pre-PR-#664 binary)")
    args = ap.parse_args()

    env.assert_no_other_qet_running(args.binary)

    seeds = sorted(args.corpus.glob("*.qet"))
    if not seeds:
        print(f"no .qet files found in {args.corpus}", file=sys.stderr)
        return 2

    any_orphaned = False
    with env.sandbox_context() as sb:
        for seed in seeds:
            orphaned, detail = check_one(args.binary, seed, sb, args.timeout)
            marker = "ORPHAN" if orphaned else "clean "
            print(f"[{marker}] {seed.name}: {detail}")
            any_orphaned = any_orphaned or orphaned

    if args.expect_bug:
        if not any_orphaned:
            print("\nFAIL (--expect-bug): expected the orphan-row bug to reproduce "
                  "somewhere in the corpus, but every file was clean.")
            return 1
        print("\nPASS (--expect-bug): orphan-row bug reproduces as expected.")
        return 0
    else:
        if any_orphaned:
            print("\nFAIL: element_info orphan row reproduced -- PR #664 regression, "
                  "or this binary predates the fix.")
            return 1
        print("\nPASS: no element_info orphan rows after delete+undo.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
