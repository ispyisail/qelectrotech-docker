"""
Unit tests for shrink.py using a synthetic, fast "reproduces" predicate --
no binary needed. Validates ddmin's correctness in isolation from
whether the real QET binary is available.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator.shrink import ddmin
from simulator.trace import Trace


def make_trace(n: int, culprits: set[int]) -> Trace:
    """A trace of n steps; args["culprit"] marks the ones that matter."""
    t = Trace(seed_name="synthetic", seed_sha256="0" * 64, seed=0)
    for i in range(n):
        t.append("noop", {"culprit": i in culprits})
    return t


class TestDdmin(unittest.TestCase):
    def test_finds_single_culprit_among_many_noise_steps(self):
        trace = make_trace(50, culprits={37})
        calls = {"count": 0}

        def reproduces(candidate: Trace) -> bool:
            calls["count"] += 1
            return any(s.args["culprit"] for s in candidate.steps)

        result = ddmin(trace, reproduces)
        self.assertEqual(len(result.steps), 1)
        self.assertTrue(result.steps[0].args["culprit"])
        # Should need far fewer than 50 replays to find a single culprit.
        self.assertLess(calls["count"], 50)

    def test_finds_two_required_culprits(self):
        # Failure requires BOTH marked steps to be present together.
        # Steps are tagged (not indexed) since ddmin renumbers on shrink.
        trace = make_trace(60, culprits=set())
        trace.steps[5].args = {"culprit": True, "tag": "A"}
        trace.steps[42].args = {"culprit": True, "tag": "B"}

        def reproduces(candidate: Trace) -> bool:
            tags = {s.args.get("tag") for s in candidate.steps if s.args.get("culprit")}
            return {"A", "B"}.issubset(tags)

        result = ddmin(trace, reproduces)
        tags = {s.args.get("tag") for s in result.steps if s.args.get("culprit")}
        self.assertEqual(tags, {"A", "B"})
        # A correct minimisation keeps at most a small handful of steps,
        # not anywhere near the original 60.
        self.assertLessEqual(len(result.steps), 10)

    def test_already_minimal_trace_is_unchanged(self):
        trace = make_trace(1, culprits={0})
        result = ddmin(trace, lambda c: any(s.args["culprit"] for s in c.steps))
        self.assertEqual(len(result.steps), 1)

    def test_empty_trace_returns_empty(self):
        trace = make_trace(0, culprits=set())
        result = ddmin(trace, lambda c: False)
        self.assertEqual(len(result.steps), 0)

    def test_all_steps_required_returns_all(self):
        trace = make_trace(8, culprits=set())

        def reproduces(candidate: Trace) -> bool:
            return len(candidate.steps) == 8  # only the full set reproduces

        result = ddmin(trace, reproduces)
        self.assertEqual(len(result.steps), 8)


if __name__ == "__main__":
    unittest.main()
