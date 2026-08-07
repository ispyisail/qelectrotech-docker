#!/usr/bin/env python3
"""
Fixture: the two bugs this simulator found and fixed upstream
(qelectrotech-source-mirror PR #682) must stay fixed.

Unlike fixture_determinism.py, this one is EXPECTED TO PASS on any
binary built after that PR merged, and is the automated version of the
gdb-and-manual-verification loop done by hand while fixing them. Run it
against a binary before and after any change to XML loading or element
geometry parsing to catch a regression immediately rather than
rediscover these by fuzzing again.

Covers, from simulator/reports/findings/manifest.json:

  nan_coordinate_hang_grafcet.qet
      A single x="nan" on one element used to spin --resave forever
      (confirmed via gdb + /proc/<pid>/stat: 100% CPU inside
      QPainterPathStroker::createStroke(), not a blocked wait). Fixed by
      QET::attributeIsAReal() rejecting non-finite values.

  nul_byte_segv_cablage.qet
      A single embedded NUL byte in XML whitespace used to SIGSEGV
      inside libQt5Xml's own QDomDocument::setContent(), never reaching
      any QET code. Fixed by QET::isWellFormedXmlByteStream() rejecting
      illegal XML control bytes before the parser sees them. The fix
      also covers 0x0E and 0x19 (see manifest.json note) -- not tested
      here again since the same code path handles all three identically
      and canon.py's own tests already prove the byte-level logic.

A timeout counts as a failure here (the hang bug reproducing looks like
a timeout, not a crash).

Usage:
    python3 -m simulator.fixtures.fixture_known_bugs --binary PATH
    python3 -m simulator.fixtures.fixture_known_bugs --binary PATH --expect-bugs
        (use against an OLD, pre-#682 binary to confirm the fixtures
        themselves still reproduce the original bugs)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import env
from simulator.proc import run_cli

FINDINGS_DIR = Path(__file__).resolve().parent.parent / "reports" / "findings"

CASES = [
    ("nan_coordinate_hang_grafcet.qet", "PR #682: non-finite element coordinate hang"),
    ("nul_byte_segv_cablage.qet", "PR #682: illegal XML control byte SIGSEGV"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--expect-bugs", action="store_true",
                     help="Invert the expectation: pass only if BOTH bugs still reproduce "
                          "(use against a pre-PR-#682 binary to sanity-check the fixtures)")
    args = ap.parse_args()

    env.assert_no_other_qet_running(args.binary)

    if not FINDINGS_DIR.exists():
        print(f"no findings directory at {FINDINGS_DIR}", file=sys.stderr)
        return 2

    any_bug_reproduced = False
    with env.sandbox_context() as sb:
        for filename, label in CASES:
            seed = FINDINGS_DIR / filename
            if not seed.exists():
                print(f"missing fixture file: {seed}", file=sys.stderr)
                return 2

            out = sb.work / f"{filename}.out.qet"
            outcome = run_cli(args.binary, ["--resave", str(seed), str(out)], sb, timeout=args.timeout)

            if outcome.crashed:
                any_bug_reproduced = True
                print(f"[{filename}] {label}: STILL BROKEN -- {outcome.crash_kind}: {outcome.crash_message}")
            else:
                print(f"[{filename}] {label}: clean (returncode={outcome.returncode})")

    if args.expect_bugs:
        if not any_bug_reproduced:
            print("\nFAIL (--expect-bugs): expected at least one of these to still reproduce, "
                  "but both were handled cleanly. Either this binary already has PR #682, or "
                  "one of the fixtures has stopped reproducing its bug for an unrelated reason.")
            return 1
        print("\nPASS (--expect-bugs): fixture(s) still reproduce as expected on this binary.")
        return 0
    else:
        if any_bug_reproduced:
            print("\nFAIL: at least one known-fixed bug reproduced again -- regression.")
            return 1
        print("\nPASS: both known bugs stay fixed.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
