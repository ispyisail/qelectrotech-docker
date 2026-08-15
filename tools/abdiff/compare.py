"""
Classify the difference between two variant runs.

Vocabulary (LAB-PLAN.md L1): same / differs / a-only-fails / b-only-fails.
Exit non-zero only on a real difference -- "same" is the only verdict
that maps to exit 0 (see tools/abdiff/__main__.py).

A run "fails" if simulator/proc.py's Outcome.crashed is set (this
already covers timeout, signal, ASan/LSan/TSan/UBSan headline, Q_ASSERT,
and qFatal -- see proc.Outcome.classify()) or it exited with an
unexplained nonzero code. One nonzero exit is explicitly NOT a failure:
--export-wires / --export-cables legitimately return 1 on an empty
result (TOOLING-PLAN.md trap #8). Without that carve-out, two variants
that both correctly report "nothing to export" on the same input would
be misclassified as both having failed, which -- per the "both failed
identically" rule below -- would still come out as `same`, but for the
wrong reason and with a misleading "failed" label in the report.

The single most important rule here, called out explicitly in the task
this module implements: A TIMEOUT ON ONE SIDE IS `a-only-fails` /
`b-only-fails`, NEVER "no output from either, therefore same". That
case is handled by the very first branch below, before any output
comparison happens -- a hung variant's (empty, truncated) stdout/stderr
never gets compared to the other side's.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from simulator import canon
from simulator.proc import Outcome

_BENIGN_EMPTY_RESULT_FLAGS = ("--export-wires", "--export-cables")

# Strip absolute filesystem paths and ISO-ish timestamps before comparing
# stdout/stderr byte-for-byte, so cosmetic churn (a random sandbox tmp
# dir name, a "compiled on" style timestamp) doesn't manufacture a
# `differs` verdict out of two runs that are semantically identical.
_PATH_LIKE = re.compile(r"/(?:tmp|home)/\S+")
_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)

# QET's qInfo() load timers (sources/qetproject.cpp) write per-run
# wall-clock timings to stderr for every CLI verb that opens a project:
#
#   Project content built in 1.8 seconds (elements collection 0.019, ...)
#   Project "perceuse.qet" (1763 KiB) opened in 1.913 seconds (xml parsing 0.109, ...)
#
# Two runs of the SAME binary on the SAME input differ only in these
# numbers, so leaving them in turns a same-vs-same --info run into a false
# `differs`. Normalize the timing numbers to a placeholder while keeping
# the structural text (filename, KiB) intact.
_QET_TIMING = re.compile(
    r"^(Project (?:content built|\"[^\"]*\" \(\d+ KiB\) opened) in )"
    r"\d+(?:\.\d+)? seconds \(([^)]*)\)$",
    re.MULTILINE,
)
_INNER_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")


def _strip_qet_timings(s: str) -> str:
    def _repl(m: re.Match) -> str:
        inner = _INNER_NUMBER.sub("<N>", m.group(2))
        return f"{m.group(1)}<N> seconds ({inner})"

    return _QET_TIMING.sub(_repl, s)

VERDICT_SAME = "same"
VERDICT_DIFFERS = "differs"
VERDICT_A_ONLY_FAILS = "a-only-fails"
VERDICT_B_ONLY_FAILS = "b-only-fails"


@dataclass
class Comparison:
    verdict: str
    reasons: list[str] = field(default_factory=list)
    a_failed: bool = False
    b_failed: bool = False


def _is_benign_nonzero(command: list[str], outcome: Outcome) -> bool:
    if outcome.returncode != 1:
        return False
    if not any(flag in command for flag in _BENIGN_EMPTY_RESULT_FLAGS):
        return False
    return "Nothing to export" in outcome.stderr


def _failed(command: list[str], outcome: Outcome) -> bool:
    if outcome.crashed:
        return True
    if outcome.returncode not in (0, None) and not _is_benign_nonzero(command, outcome):
        return True
    return False


def _fail_reason(label: str, outcome: Outcome) -> str:
    if outcome.timed_out:
        return f"variant {label} timed out after {outcome.wall_seconds:.1f}s (no completion)"
    if outcome.crashed:
        return f"variant {label} crashed ({outcome.crash_kind}): {outcome.crash_message}"
    return f"variant {label} exited {outcome.returncode}"


def _normalize(s: str, *, extra_roots: list[str]) -> str:
    out = s
    for root in extra_roots:
        if root:
            out = out.replace(root, "<SANDBOX>")
    out = _strip_qet_timings(out)
    out = _PATH_LIKE.sub("<PATH>", out)
    out = _TIMESTAMP.sub("<TIMESTAMP>", out)
    return out


def _text_diff(label: str, a: str, b: str) -> str | None:
    if a == b:
        return None
    lines = list(difflib.unified_diff(
        a.splitlines(), b.splitlines(), f"A {label}", f"B {label}", lineterm=""
    ))
    return f"{label} differs:\n" + "\n".join(lines[:40])


def _diff_produced_files(dir_a: Path, dir_b: Path) -> list[str]:
    reasons: list[str] = []
    names_a = {p.relative_to(dir_a).as_posix() for p in dir_a.rglob("*") if p.is_file()}
    names_b = {p.relative_to(dir_b).as_posix() for p in dir_b.rglob("*") if p.is_file()}
    only_a, only_b = names_a - names_b, names_b - names_a
    if only_a:
        reasons.append(f"file(s) only produced by A: {sorted(only_a)}")
    if only_b:
        reasons.append(f"file(s) only produced by B: {sorted(only_b)}")

    for name in sorted(names_a & names_b):
        pa, pb = dir_a / name, dir_b / name
        if name.endswith(".qet") or name.endswith(".elmt"):
            # Semantic diff, not byte-for-byte -- a resave's cosmetic
            # churn (attribute order, whitespace) must not fail this.
            try:
                ca, cb = canon.canonicalize(pa), canon.canonicalize(pb)
            except canon.CanonError as e:
                reasons.append(f"{name}: could not canonicalize -- {e}")
                continue
            d = canon.diff(ca, cb)
            if d:
                reasons.append(f"{name} differs (semantic): " + "; ".join(d))
        else:
            if pa.read_bytes() != pb.read_bytes():
                reasons.append(f"{name} differs (byte-for-byte)")
    return reasons


def compare(
    command: list[str],
    outcome_a: Outcome,
    outcome_b: Outcome,
    produced_a: Path,
    produced_b: Path,
) -> Comparison:
    fail_a = _failed(command, outcome_a)
    fail_b = _failed(command, outcome_b)

    # --- the case that matters most: a failure/timeout on exactly one
    # side is a first-class, non-zero-exit verdict. Nothing below this
    # point runs for that case -- in particular a hung variant's
    # (empty/partial) stdout is never diffed against the other side's.
    if fail_a and not fail_b:
        return Comparison(VERDICT_A_ONLY_FAILS, [_fail_reason("A", outcome_a)], True, False)
    if fail_b and not fail_a:
        return Comparison(VERDICT_B_ONLY_FAILS, [_fail_reason("B", outcome_b)], False, True)

    if fail_a and fail_b:
        # Both sides failed. Whether that counts as `same` or `differs`
        # depends on whether they failed the *same way* -- e.g. running
        # the same ref against itself and hanging both times is `same`
        # (LAB-PLAN.md L1: "same-vs-same ... with any command must
        # report same"), but A timing out while B ASan-crashes is not.
        reasons = []
        if outcome_a.crash_kind != outcome_b.crash_kind:
            reasons.append(f"crash kind differs: {outcome_a.crash_kind!r} vs {outcome_b.crash_kind!r}")
        if outcome_a.returncode != outcome_b.returncode:
            reasons.append(f"exit code differs: {outcome_a.returncode!r} vs {outcome_b.returncode!r}")
        verdict = VERDICT_DIFFERS if reasons else VERDICT_SAME
        if not reasons:
            reasons.append(
                f"both variants failed the same way "
                f"({outcome_a.crash_kind or outcome_a.returncode})"
            )
        return Comparison(verdict, reasons, True, True)

    # --- neither side failed: compare exit code, normalized
    # stdout/stderr, and anything either run wrote to disk.
    reasons: list[str] = []
    if outcome_a.returncode != outcome_b.returncode:
        reasons.append(f"exit code differs: {outcome_a.returncode} vs {outcome_b.returncode}")

    roots = [outcome_a.sandbox_root, outcome_b.sandbox_root]
    for label, a_text, b_text in (
        ("stdout", outcome_a.stdout, outcome_b.stdout),
        ("stderr", outcome_a.stderr, outcome_b.stderr),
    ):
        d = _text_diff(label, _normalize(a_text, extra_roots=roots), _normalize(b_text, extra_roots=roots))
        if d:
            reasons.append(d)

    reasons.extend(_diff_produced_files(produced_a, produced_b))

    verdict = VERDICT_DIFFERS if reasons else VERDICT_SAME
    return Comparison(verdict, reasons, False, False)
