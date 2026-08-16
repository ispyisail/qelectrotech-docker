"""
Classify one per-(project, verb) A/B comparison as regression / improvement /
change / same.

The per-command comparison itself (same / differs / a-only-fails /
b-only-fails, with crash/timeout/exit-code/stdout/stderr/produced-file
semantics) lives in `tools.abdiff.compare` and is reused unchanged. This
module adds the one thing W3 needs that the single-command harness does not:
a *direction*. `differs` is not enough -- the sweep must say whether the
head got worse, better, or merely different.

Direction comes from two places:

  - a failure that exists on exactly one side (from `Comparison`): base
    fails + head passes = improvement; the reverse = regression.
  - for `--resave`, a structured content delta between the two canonicalised
    `.qet` outputs (`simulator.canon`): head losing elements/conductors/uuids
    = regression, head gaining them = improvement, neither = change.

Text exports (`--info`, `--export-bom`, `--export-nets`, `--export-links`)
have no intrinsic better/worse direction, so a difference there is `change`
unless it came from a one-sided failure. That is deliberate: the `.qet`
resave is the authoritative content check; if a text export disagrees with it
the report says so as a `change`, but it is the resave that decides
regression vs improvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from simulator import canon
from tools.abdiff.compare import (
    VERDICT_A_ONLY_FAILS,
    VERDICT_B_ONLY_FAILS,
    VERDICT_DIFFERS,
    VERDICT_SAME,
    Comparison,
)

CATEGORY_SAME = "same"
CATEGORY_REGRESSION = "regression"
CATEGORY_IMPROVEMENT = "improvement"
CATEGORY_CHANGE = "change"

# How many uuids/keys to spell out in a reason before eliding.
_LIST_LIMIT = 20


@dataclass
class ContentDelta:
    """Structured base-vs-head delta over the identity-bearing parts of two
    canonicalised `.qet` projects (see simulator/canon.py for what counts as
    identity-bearing)."""
    lost_elements: list[str] = field(default_factory=list)    # element uuids
    gained_elements: list[str] = field(default_factory=list)
    lost_conductors: list[str] = field(default_factory=list)  # canon conductor keys
    gained_conductors: list[str] = field(default_factory=list)
    lost_uuids: list[str] = field(default_factory=list)       # whole uuid universe
    gained_uuids: list[str] = field(default_factory=list)

    @property
    def any_loss(self) -> bool:
        return bool(self.lost_elements or self.lost_conductors or self.lost_uuids)

    @property
    def any_gain(self) -> bool:
        return bool(self.gained_elements or self.gained_conductors or self.gained_uuids)

    @property
    def empty(self) -> bool:
        return not (self.any_loss or self.any_gain)


def content_delta(base: canon.Canon, head: canon.Canon) -> ContentDelta:
    base_elements = {u for d in base.diagrams for u in d["elements"]}
    head_elements = {u for d in head.diagrams for u in d["elements"]}
    base_conductors = {k for d in base.diagrams for k in d["conductors"]}
    head_conductors = {k for d in head.diagrams for k in d["conductors"]}
    base_uuids = set(base.uuid_universe)
    head_uuids = set(head.uuid_universe)
    return ContentDelta(
        lost_elements=sorted(base_elements - head_elements),
        gained_elements=sorted(head_elements - base_elements),
        lost_conductors=sorted(base_conductors - head_conductors),
        gained_conductors=sorted(head_conductors - base_conductors),
        lost_uuids=sorted(base_uuids - head_uuids),
        gained_uuids=sorted(head_uuids - base_uuids),
    )


def _list(xs: list[str]) -> str:
    shown = ", ".join(xs[:_LIST_LIMIT])
    if len(xs) > _LIST_LIMIT:
        shown += f" ... (+{len(xs) - _LIST_LIMIT} more)"
    return shown


def delta_reasons(delta: ContentDelta) -> list[str]:
    """Human-readable reasons for a content delta, naming the lost/gained
    uuids so a regression report says *what* vanished, not just that it did."""
    reasons: list[str] = []
    if delta.lost_elements:
        reasons.append(f"head lost {len(delta.lost_elements)} element(s): {_list(delta.lost_elements)}")
    if delta.gained_elements:
        reasons.append(f"head gained {len(delta.gained_elements)} element(s): {_list(delta.gained_elements)}")
    if delta.lost_conductors:
        reasons.append(f"head lost {len(delta.lost_conductors)} conductor(s)")
    if delta.gained_conductors:
        reasons.append(f"head gained {len(delta.gained_conductors)} conductor(s)")
    # uuids that are not element uuids (terminals, dynamic texts, ...) -- the
    # element list above already covers element uuids, so de-duplicate here.
    other_lost = sorted(set(delta.lost_uuids) - set(delta.lost_elements))
    other_gained = sorted(set(delta.gained_uuids) - set(delta.gained_elements))
    if other_lost:
        reasons.append(f"head lost {len(other_lost)} other uuid(s) (terminals/texts/etc): {_list(other_lost)}")
    if other_gained:
        reasons.append(f"head gained {len(other_gained)} other uuid(s) (terminals/texts/etc): {_list(other_gained)}")
    return reasons


def classify(
    comparison: Comparison,
    delta: ContentDelta | None = None,
) -> tuple[str, list[str]]:
    """Return (category, reasons) for one per-(project, verb) comparison.

    `delta` is the content delta for the produced `.qet` (resave) file, or
    None for the text-export verbs. Regression is the only category the
    caller maps to a non-zero exit code.
    """
    if comparison.verdict == VERDICT_SAME:
        return CATEGORY_SAME, []

    # One-sided failure: the direction is unambiguous and independent of any
    # content delta.
    if comparison.verdict == VERDICT_A_ONLY_FAILS:
        return CATEGORY_IMPROVEMENT, comparison.reasons
    if comparison.verdict == VERDICT_B_ONLY_FAILS:
        return CATEGORY_REGRESSION, comparison.reasons

    # `differs`: decide by content loss/gain when we have a delta, else it is
    # a semantic difference with no obvious direction.
    if delta is not None and not delta.empty:
        reasons = delta_reasons(delta)
        if delta.any_loss:
            return CATEGORY_REGRESSION, reasons
        return CATEGORY_IMPROVEMENT, reasons

    return CATEGORY_CHANGE, comparison.reasons


def resave_delta(produced_base: Path, produced_head: Path, out_name: str = "out.qet") -> ContentDelta | None:
    """Canonicalise the two produced `.qet` files and return their delta,
    or None if either side produced no parseable `.qet` (in which case the
    file-level difference is already in `Comparison.reasons`)."""
    pa, pb = produced_base / out_name, produced_head / out_name
    if not (pa.exists() and pb.exists()):
        return None
    try:
        ca = canon.canonicalize(pa)
        cb = canon.canonicalize(pb)
    except canon.CanonError:
        return None
    return content_delta(ca, cb)
