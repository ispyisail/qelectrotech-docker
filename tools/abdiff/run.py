"""
Run one variant's command inside an isolated simulator/env.py sandbox and
classify it with simulator/proc.py's run_cli() -- no hand-rolled
subprocess handling here, per LAB-PLAN.md L1's explicit instruction.

The critical property this module exists to guarantee: a variant that
hangs can never block, corrupt, or extend the *other* variant's run.
run_cli()'s subprocess.run(timeout=...) already kills the child and
raises TimeoutExpired on expiry (Python's own doing, not ours), so a
single call to run_variant() never blocks longer than `timeout` no
matter what the target does. Two sequential calls (variant A then
variant B) therefore bound the whole harness's wall time at
2 * timeout in the worst case, never at infinity.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from simulator import env
from simulator.proc import Outcome, run_cli


def run_variant(
    binary: Path,
    command: list[str],
    *,
    timeout: float,
    produced_dir: Path,
) -> Outcome:
    """Run `binary command...` in a fresh sandbox and copy out anything
    the run wrote to its working directory (e.g. a --resave output file)
    into `produced_dir` before the sandbox is torn down, so compare.py
    can still read it afterwards."""
    env.assert_no_other_qet_running(str(binary))
    produced_dir.mkdir(parents=True, exist_ok=True)

    with env.sandbox_context() as sb:
        outcome = run_cli(str(binary), command, sb, timeout=timeout)
        for p in sb.work.rglob("*"):
            if p.is_file():
                dest = produced_dir / p.relative_to(sb.work)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)

    return outcome
