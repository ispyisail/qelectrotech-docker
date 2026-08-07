"""
Unit tests for oracles.py using real corpus files and synthetic
canon.Canon objects. No qelectrotech binary needed -- these test the
oracle FUNCTIONS, not whether the real binary triggers them (that is
covered by simulator/fixtures/fixture_determinism.py, which does need
the binary).
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import canon, oracles
from simulator.proc import Outcome

SAMPLE = Path("/home/user/qet-fix/examples/741.qet")
TMP = Path("/tmp/claude-1000-oracles-test")


def _write(text: str, name: str) -> Path:
    TMP.mkdir(exist_ok=True)
    p = TMP / name
    p.write_text(text)
    return p


def make_outcome(**kwargs) -> Outcome:
    defaults = dict(argv=["x"], returncode=0, signal=None, stdout="", stderr="",
                     wall_seconds=0.1, timed_out=False, sandbox_root="/tmp/x")
    defaults.update(kwargs)
    return Outcome(**defaults)


class TestO1Crash(unittest.TestCase):
    def test_clean_outcome_has_no_finding(self):
        o = make_outcome().classify()
        self.assertEqual(oracles.o1_crash(o), [])

    def test_crashed_outcome_produces_a_finding(self):
        o = make_outcome(timed_out=True, returncode=None).classify()
        findings = oracles.o1_crash(o)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].oracle, "O1")
        self.assertEqual(findings[0].severity, "crash")


class TestO2Idempotence(unittest.TestCase):
    def test_identical_files_pass(self):
        self.assertEqual(oracles.o2_idempotence(SAMPLE, SAMPLE), [])

    def test_differing_files_fail(self):
        text = SAMPLE.read_text()
        mutated = re.sub(r"<element .*?</element>", "", text, count=1, flags=re.S)
        p = _write(mutated, "o2_diff.qet")
        findings = oracles.o2_idempotence(SAMPLE, p)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].oracle, "O2")
        self.assertIn("diffs", findings[0].detail)

    def test_unparseable_file_reports_corruption_not_a_crash(self):
        p = _write("<not well formed", "o2_broken.qet")
        findings = oracles.o2_idempotence(SAMPLE, p)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "corruption")


class TestO3SemanticPreservation(unittest.TestCase):
    def test_identical_files_pass(self):
        self.assertEqual(oracles.o3_semantic_preservation(SAMPLE, SAMPLE), [])

    def test_dropped_element_is_reported_as_lost_uuid(self):
        text = SAMPLE.read_text()
        m = re.search(r'<element .*?</element>', text, re.S)
        uuid_m = re.search(r'uuid="([^"]+)"', m.group(0))
        mutated = text[: m.start()] + text[m.end():]
        p = _write(mutated, "o3_dropped.qet")
        findings = oracles.o3_semantic_preservation(SAMPLE, p)
        self.assertTrue(findings)
        lost = findings[0].detail["lost_uuids"]
        self.assertIn(uuid_m.group(1), lost)

    def test_element_count_change_is_reported(self):
        text = SAMPLE.read_text()
        mutated = re.sub(r"<element .*?</element>", "", text, count=1, flags=re.S)
        p = _write(mutated, "o3_count.qet")
        findings = oracles.o3_semantic_preservation(SAMPLE, p)
        messages = [f.message for f in findings]
        self.assertTrue(any("element count changed" in m for m in messages))


class TestO6NanInf(unittest.TestCase):
    def test_clean_file_passes(self):
        self.assertEqual(oracles.o6_nan_inf(SAMPLE), [])

    def test_injected_nan_is_caught(self):
        text = SAMPLE.read_text()
        mutated, n = re.subn(r'(<element [^>]*\bx=")(\d+)(")', r'\1nan\3', text, count=1)
        self.assertEqual(n, 1)
        p = _write(mutated, "o6_nan.qet")
        findings = oracles.o6_nan_inf(p)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].oracle, "O6")


class TestO6GridRegression(unittest.TestCase):
    def test_self_compare_passes(self):
        self.assertEqual(oracles.o6_grid_regression(SAMPLE, SAMPLE), [])

    def test_pushed_off_grid_is_caught(self):
        text = SAMPLE.read_text()
        m = re.search(r'<element [^>]*\bx="(\d+)"', text)
        x0 = int(m.group(1))
        self.assertEqual(x0 % 10, 0)
        mutated = text.replace(f'x="{x0}"', f'x="{x0 + 3}"', 1)
        before = _write(text, "o6grid_before.qet")
        after = _write(mutated, "o6grid_after.qet")
        findings = oracles.o6_grid_regression(before, after, grid=10)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].oracle, "O6")
        self.assertEqual(findings[0].severity, "regression")


class TestO9Determinism(unittest.TestCase):
    def test_identical_canon_passes(self):
        c = canon.canonicalize(SAMPLE)
        self.assertEqual(oracles.o9_determinism(c, c, "self"), [])

    def test_differing_canon_fails_loudly(self):
        c1 = canon.canonicalize(SAMPLE)
        text = SAMPLE.read_text()
        mutated = re.sub(r"<element .*?</element>", "", text, count=1, flags=re.S)
        p = _write(mutated, "o9_diff.qet")
        c2 = canon.canonicalize(p)
        findings = oracles.o9_determinism(c1, c2, "test-context")
        self.assertEqual(len(findings), 1)
        self.assertIn("test-context", findings[0].message)
        self.assertIn("suspect", findings[0].message)


class TestFindingSerialization(unittest.TestCase):
    def test_to_dict_is_json_safe(self):
        import json
        f = oracles.Finding("O2", "corruption", "msg", {"a": [1, 2], "b": "x"})
        json.dumps(f.to_dict())  # must not raise


if __name__ == "__main__":
    unittest.main()
