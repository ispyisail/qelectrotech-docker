"""
Run the qelectrotech binary's headless CLI (sources/cli_export.cpp) inside
an isolated sandbox and classify the result.

Deliberately independent of fuzzer/monitor.py (no __init__.py there, and
that module is tuned for a long-running GUI subprocess under xdotool,
not a short CLI invocation) but reuses the same sanitizer-output pattern
so a crash found here is recognisable in the same shape as one found by
the GUI fuzzer.
"""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from simulator.env import Sandbox

# NOTE: fuzzer/monitor.py's _ASAN_HEADLINE requires \s+ between the closing
# "==" and "ERROR:". Real sanitizer output has NO whitespace there --
# verified against tests/asan-regression/raw/*.out, e.g. literally
# "==22==ERROR: LeakSanitizer:" -- so that pattern (and this one, before
# the fix below) would never match genuine ASan/LSan/UBSan/TSan output.
# Found by simulator/tests/test_proc.py failing against a real .out
# sample; not yet reported/fixed upstream in fuzzer/monitor.py itself.
_ASAN_HEADLINE = re.compile(
    r"=+\d+=+ERROR:\s+(AddressSanitizer|LeakSanitizer|ThreadSanitizer|"
    r"UndefinedBehaviorSanitizer):\s+(.+)"
)
_QFATAL = re.compile(r"^(QFATAL|Fatal:)\s+(.+)", re.MULTILINE)
_QASSERT = re.compile(r"ASSERT:\s+\"(.+?)\"\s+in file\s+(.+)")


@dataclass
class Outcome:
    """The full, classified result of one CLI invocation."""

    argv: list[str]
    returncode: int | None
    signal: int | None
    stdout: str
    stderr: str
    wall_seconds: float
    timed_out: bool
    sandbox_root: str

    # classification, filled in by classify()
    crashed: bool = field(default=False)
    crash_kind: str | None = None
    crash_message: str | None = None

    def classify(self) -> "Outcome":
        if self.timed_out:
            self.crashed = True
            self.crash_kind = "timeout"
            self.crash_message = f"no completion after {self.wall_seconds:.1f}s"
            return self

        # Self-contained on purpose: don't rely on the caller (normally
        # run_cli) having already derived `signal` from a negative
        # returncode. An Outcome reconstructed from a saved report, or
        # built directly in a test, must classify correctly on its own.
        if self.signal is None and self.returncode is not None and self.returncode < 0:
            self.signal = -self.returncode

        if self.signal is not None:
            self.crashed = True
            self.crash_kind = "signal"
            self.crash_message = f"terminated by signal {self.signal}"
            return self

        m = _ASAN_HEADLINE.search(self.stderr)
        if m:
            self.crashed = True
            self.crash_kind = m.group(1)
            self.crash_message = m.group(2).strip()
            return self

        m = _QASSERT.search(self.stderr)
        if m:
            self.crashed = True
            self.crash_kind = "Q_ASSERT"
            self.crash_message = f'"{m.group(1)}" in {m.group(2)}'
            return self

        m = _QFATAL.search(self.stderr)
        if m:
            self.crashed = True
            self.crash_kind = "qFatal"
            self.crash_message = m.group(2).strip()
            return self

        return self

    def to_dict(self) -> dict:
        return {
            "argv": self.argv,
            "returncode": self.returncode,
            "signal": self.signal,
            "wall_seconds": round(self.wall_seconds, 3),
            "timed_out": self.timed_out,
            "crashed": self.crashed,
            "crash_kind": self.crash_kind,
            "crash_message": self.crash_message,
            "stdout_tail": self.stdout[-4000:],
            "stderr_tail": self.stderr[-4000:],
        }


def run_cli(
    binary: str,
    args: list[str],
    sandbox: Sandbox,
    *,
    timeout: float = 30.0,
    cwd: Path | None = None,
) -> Outcome:
    """
    Invoke `binary args...` inside `sandbox`. Never raises on a crashing
    or hanging target -- that is exactly the thing under test, so it is
    reported through Outcome, not through a Python exception. Only truly
    exceptional conditions (binary missing) raise.
    """
    argv = [binary, *args]
    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd or sandbox.work),
            env=sandbox.child_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        returncode = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        returncode = None
        stdout = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")

    wall = time.monotonic() - start
    signal = None
    if returncode is not None and returncode < 0:
        signal = -returncode

    return Outcome(
        argv=argv,
        returncode=returncode,
        signal=signal,
        stdout=stdout,
        stderr=stderr,
        wall_seconds=wall,
        timed_out=timed_out,
        sandbox_root=str(sandbox.root),
    ).classify()
