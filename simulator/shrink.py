"""
Delta-debugging (ddmin) over a Trace.

Per SIMULATOR-DESIGN.md §4.4: this is the difference between a tool
people use and a tool that produces logs nobody reads. Turns "4,000
mutations, seed 12345, failed somewhere" into the 1-3 steps that actually
matter. Only works because trace.py + mutate.apply_resolved() guarantee
exact replay without the RNG -- ddmin re-runs the SAME steps repeatedly
and depends on that being deterministic.
"""
from __future__ import annotations

from typing import Callable

from simulator.trace import Trace


def ddmin(trace: Trace, reproduces: Callable[[Trace], bool]) -> Trace:
    """
    Classic ddmin (Zeller & Hildebrandt). `reproduces(candidate_trace)`
    must return True iff replaying `candidate_trace` still triggers the
    same failure. Assumes `reproduces(trace)` is already True for the
    input -- callers should verify that once, up front, rather than
    inside the loop (it would otherwise be re-checked O(n) times for no
    benefit).

    Returns a new Trace containing a minimal (not necessarily globally
    minimum -- ddmin is a heuristic) subset of steps that still
    reproduces the failure, renumbered from 0.
    """
    indices = list(range(len(trace.steps)))
    if not indices:
        return trace.sub_trace([])

    n = 2
    while len(indices) >= 1:
        chunk_size = max(1, len(indices) // n)
        chunks = [indices[i:i + chunk_size] for i in range(0, len(indices), chunk_size)]
        if len(chunks) < 2:
            break

        reduced = False

        # Try removing each chunk (the "complement" test).
        for chunk in chunks:
            complement = [i for i in indices if i not in chunk]
            if not complement:
                continue
            candidate = trace.sub_trace(complement)
            if reproduces(candidate):
                indices = complement
                n = max(n - 1, 2)
                reduced = True
                break
        if reduced:
            continue

        # Try keeping ONLY each chunk in isolation.
        for chunk in chunks:
            if len(chunk) == len(indices):
                continue
            candidate = trace.sub_trace(chunk)
            if reproduces(candidate):
                indices = chunk
                n = 2
                reduced = True
                break
        if reduced:
            continue

        if n >= len(indices):
            break
        n = min(n * 2, len(indices))

    return trace.sub_trace(indices)
