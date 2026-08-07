#!/usr/bin/env python3
"""
Fixture: O2 (resave idempotence) against a REAL, currently-open QET bug.

Per SIMULATOR-DESIGN.md §10, success is defined as rediscovering known
defects, written as fixtures BEFORE the generator existed -- "a harness
that cannot catch a bug you already understand will not catch one you
don't." This is fixture #4 of that list (the other three -- PR #664,
#660, #668 -- need interactive/undo sequences the headless CLI can't
drive; see simulator/README.md "Known gap").

This fixture is EXPECTED TO FAIL (i.e. find a violation) as long as
tests/determinism/check.py's I1 is unresolved upstream. That is the
point: it proves the harness, using nothing but its own oracle.py and
canon.py, independently rediscovers a real, previously-documented,
currently-open bug -- not a synthetic one built to be found.

Usage:
    python3 -m simulator.fixtures.fixture_determinism --binary /path/to/qelectrotech
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import canon, env, oracles
from simulator.proc import run_cli

DEFAULT_CORPUS = Path("/home/user/qet-fix/examples")


def check_one(binary: str, seed: Path, sandbox: env.Sandbox) -> list[oracles.Finding]:
    r1 = sandbox.work / f"{seed.stem}.r1.qet"
    r2 = sandbox.work / f"{seed.stem}.r2.qet"

    o1 = run_cli(binary, ["--resave", str(seed), str(r1)], sandbox, timeout=30)
    if o1.crashed or not r1.exists():
        return oracles.o1_crash(o1)

    o2 = run_cli(binary, ["--resave", str(r1), str(r2)], sandbox, timeout=30)
    if o2.crashed or not r2.exists():
        return oracles.o1_crash(o2)

    return oracles.o2_idempotence(r1, r2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--expect-clean", action="store_true",
                     help="Invert the expectation: pass only if NO violation is found "
                          "(use this once tests/determinism's I1 is actually fixed upstream)")
    args = ap.parse_args()

    env.assert_no_other_qet_running(args.binary)

    seeds = sorted(args.corpus.glob("*.qet"))
    if not seeds:
        print(f"no .qet files found in {args.corpus}", file=sys.stderr)
        return 2

    any_finding = False
    with env.sandbox_context() as sb:
        for seed in seeds:
            findings = check_one(args.binary, seed, sb)
            if findings:
                any_finding = True
                print(f"[{seed.name}] {len(findings)} finding(s):")
                for f in findings:
                    print(f"  {f.oracle} ({f.severity}): {f.message}")
                    if f.oracle == "O2":
                        for d in f.detail.get("diffs", []):
                            print(f"      {d}")

    if args.expect_clean:
        if any_finding:
            print("\nFAIL: expected a clean run (--expect-clean) but found violations above.")
            return 1
        print("\nPASS: no O2 violations -- the determinism gap appears to be fixed.")
        return 0
    else:
        if not any_finding:
            print("\nUNEXPECTED PASS: this fixture is supposed to rediscover a known-open bug "
                  "(tests/determinism I1) and found nothing. Either the bug was fixed upstream "
                  "(rerun with --expect-clean to confirm) or this fixture/oracle has regressed.")
            return 1
        print(f"\nEXPECTED FAIL: rediscovered the known-open resave-idempotence bug across "
              f"{sum(1 for _ in seeds)} corpus file(s), using nothing but simulator/canon.py "
              f"and simulator/oracles.py. This is fixture success, not harness failure.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
