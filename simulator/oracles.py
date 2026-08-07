"""
Named oracles, each returning a list of Finding.

An empty list means the oracle is satisfied. Every oracle here maps
directly to a numbered oracle in SIMULATOR-DESIGN.md §3; the docstring
cites which one and why, since "which invariant does this check" is
exactly the information a prose crash log throws away.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simulator import canon
from simulator.proc import Outcome


@dataclass
class Finding:
    oracle: str          # "O1", "O2", ...
    severity: str        # "crash", "corruption", "regression"
    message: str
    detail: dict[str, Any]

    def to_dict(self) -> dict:
        return {"oracle": self.oracle, "severity": self.severity,
                "message": self.message, "detail": self.detail}


def o1_crash(outcome: Outcome) -> list[Finding]:
    """O1: process death or a sanitizer firing. See proc.Outcome.classify()."""
    if not outcome.crashed:
        return []
    return [Finding(
        "O1", "crash",
        f"{outcome.crash_kind}: {outcome.crash_message}",
        {"argv": outcome.argv, "wall_seconds": outcome.wall_seconds},
    )]


def o2_idempotence(resave1: Path, resave2: Path) -> list[Finding]:
    """
    O2: resave(resave(x)) must equal resave(x). Absorbs the property
    tests/determinism/check.py calls I1, known to fail on master.
    """
    try:
        c1, c2 = canon.canonicalize(resave1), canon.canonicalize(resave2)
    except canon.CanonError as e:
        return [Finding("O2", "corruption", f"could not parse a resave output: {e}",
                         {"resave1": str(resave1), "resave2": str(resave2)})]
    d = canon.diff(c1, c2)
    if not d:
        return []
    return [Finding(
        "O2", "corruption",
        "resave is not idempotent -- a second resave produced a different canonical state",
        {"diffs": d, "resave1": str(resave1), "resave2": str(resave2)},
    )]


def o3_semantic_preservation(before: Path, after: Path) -> list[Finding]:
    """
    O3: element/conductor/uuid counts and the full uuid set survive a
    resave. Unlike O2, a failure here is data loss regardless of any
    roadmap -- it must never regress.
    """
    try:
        ca, cb = canon.canonicalize(before), canon.canonicalize(after)
    except canon.CanonError as e:
        return [Finding("O3", "corruption", f"could not parse: {e}",
                         {"before": str(before), "after": str(after)})]

    findings = []
    ua, ub = set(ca.uuid_universe), set(cb.uuid_universe)
    lost = ua - ub
    if lost:
        findings.append(Finding(
            "O3", "corruption",
            f"{len(lost)} uuid(s) present before are missing after (data loss)",
            {"lost_uuids": sorted(lost)[:20], "before": str(before), "after": str(after)},
        ))
    gained = ub - ua
    if gained:
        findings.append(Finding(
            "O3", "corruption",
            f"{len(gained)} uuid(s) appeared that were not present before (data invented)",
            {"gained_uuids": sorted(gained)[:20], "before": str(before), "after": str(after)},
        ))
    if ca.counts["elements"] != cb.counts["elements"]:
        findings.append(Finding(
            "O3", "corruption",
            f"element count changed: {ca.counts['elements']} -> {cb.counts['elements']}",
            {"before": str(before), "after": str(after)},
        ))
    return findings


def o6_nan_inf(path: Path) -> list[Finding]:
    """O6 (absolute half): no coordinate should ever be NaN/Inf. See canon.py's
    module docstring for why grid alignment is NOT checked absolutely."""
    v = canon.nan_or_inf_violations(path)
    if not v:
        return []
    return [Finding(
        "O6", "corruption",
        f"{len(v)} NaN/Inf coordinate(s) found",
        {"violations": [vars(x) for x in v[:20]], "path": str(path)},
    )]


def o6_grid_regression(before: Path, after: Path, grid: int = 10) -> list[Finding]:
    """O6 (delta half): an element on-grid before must stay on-grid after.
    This is the property PR #660 (group rotation drifting off-grid) sat in."""
    regs = canon.grid_regressions(before, after, grid=grid)
    if not regs:
        return []
    return [Finding(
        "O6", "regression",
        f"{len(regs)} element(s) were on-grid and are no longer",
        {"regressions": [vars(x) for x in regs[:20]], "before": str(before), "after": str(after)},
    )]


def o9_determinism(canon_a: canon.Canon, canon_b: canon.Canon, context: str) -> list[Finding]:
    """
    O9: run the harness itself twice on identical inputs and require
    identical canonical output. If this fails, the SIMULATOR is
    unreliable and every other finding in the same run is suspect --
    per SIMULATOR-DESIGN.md §3, this should be checked first.
    """
    d = canon.diff(canon_a, canon_b)
    if not d:
        return []
    return [Finding(
        "O9", "corruption",
        f"harness determinism check failed ({context}): identical input produced "
        f"different canonical output -- treat every other finding from this run as suspect",
        {"diffs": d},
    )]
