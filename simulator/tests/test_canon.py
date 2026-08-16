"""
Unit tests for canon.py. No qelectrotech binary needed -- these only
exercise the XML projection logic against the real examples corpus.

Per SIMULATOR-DESIGN.md §4.3: canon() is the highest-risk component in
the harness (too strict -> false positives, too loose -> hides bugs), so
it gets tested from BOTH directions:

  - test_detects_*        : deliberately corrupted files MUST differ
  - test_tolerates_*       : purely cosmetic edits must NOT differ

A canon() that only passes the first kind of test is not proven; it
could just be diffing raw XML strings.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import canon

EXAMPLES = Path("/home/user/qet-fix/examples")
SAMPLE = EXAMPLES / "741.qet"


def _write_variant(tmp_path: Path, text: str, name: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


class TestCanonReflexive(unittest.TestCase):
    def test_self_equal(self):
        self.assertTrue(SAMPLE.exists(), f"fixture corpus missing: {SAMPLE}")
        a = canon.canonicalize(SAMPLE)
        b = canon.canonicalize(SAMPLE)
        self.assertEqual(canon.diff(a, b), [])
        self.assertTrue(canon.canon_equal(a, b))

    def test_nonempty_real_project(self):
        c = canon.canonicalize(SAMPLE)
        self.assertGreater(c.counts["elements"], 0)
        self.assertGreater(c.counts["uuids"], 0)
        self.assertGreaterEqual(c.counts["diagrams"], 1)


class TestCanonDetectsCorruption(unittest.TestCase):
    """canon() must not be too loose."""

    def setUp(self):
        self.text = SAMPLE.read_text()
        self.tmp = Path("/tmp/claude-1000-canon-test")
        self.tmp.mkdir(exist_ok=True)

    def test_detects_dropped_element(self):
        # Remove the first <element ...>...</element> block entirely.
        mutated = re.sub(r"<element .*?</element>", "", self.text, count=1, flags=re.S)
        p = _write_variant(self.tmp, mutated, "dropped_element.qet")
        a = canon.canonicalize(SAMPLE)
        b = canon.canonicalize(p)
        d = canon.diff(a, b)
        self.assertTrue(d, "dropping an element must produce a canon diff")

    def test_detects_moved_element(self):
        # Shift the first element's x by a large, unambiguous amount.
        mutated, n = re.subn(r'(<element [^>]*\bx=")(\d+)(")', lambda m: f'{m.group(1)}{int(m.group(2)) + 999}{m.group(3)}',
                              self.text, count=1)
        self.assertEqual(n, 1, "test setup: expected to find an element x= attribute")
        p = _write_variant(self.tmp, mutated, "moved_element.qet")
        d = canon.diff(canon.canonicalize(SAMPLE), canon.canonicalize(p))
        self.assertTrue(d, "moving an element must produce a canon diff")

    def test_detects_uuid_swap(self):
        # Swap two element uuids -- same count, same positions, different identity.
        uuids = re.findall(r'<element [^>]*uuid="(\{[0-9a-f-]+\})"', self.text)
        self.assertGreaterEqual(len(uuids), 2, "test setup: need >=2 elements")
        u1, u2 = uuids[0], uuids[1]
        placeholder = "{00000000-0000-0000-0000-000000000000}"
        mutated = self.text.replace(u1, placeholder, 1).replace(u2, u1, 1).replace(placeholder, u2, 1)
        p = _write_variant(self.tmp, mutated, "swapped_uuid.qet")
        d = canon.diff(canon.canonicalize(SAMPLE), canon.canonicalize(p))
        self.assertTrue(d, "swapping element uuids must produce a canon diff")

    def test_detects_conductor_rewire(self):
        mutated, n = re.subn(r'(<conductor [^>]*\bterminal2=")(\d+)(")',
                              lambda m: f'{m.group(1)}{int(m.group(2)) + 500}{m.group(3)}',
                              self.text, count=1)
        self.assertEqual(n, 1, "test setup: expected a conductor terminal2 attribute")
        p = _write_variant(self.tmp, mutated, "rewired_conductor.qet")
        d = canon.diff(canon.canonicalize(SAMPLE), canon.canonicalize(p))
        self.assertTrue(d, "rewiring a conductor's terminal must produce a canon diff")

    def test_detects_rewire_to_real_terminal(self):
        # Rewire one conductor between two DIFFERENT real terminals (not an
        # out-of-range integer that falls back to the raw "?" key). This is
        # the anti-blindness half of option A: the content-derived identity
        # -- not just the "?" fallback -- must notice the change.
        m = re.search(r'<conductor [^>]*\bterminal1="(\d+)"[^>]*\bterminal2="(\d+)"', self.text)
        self.assertIsNotNone(m, "test setup: expected a conductor with integer terminals")
        a, b = m.group(1), m.group(2)
        all_ids = set(re.findall(r'<terminal [^>]*\bid="(\d+)"', self.text))
        c = next((i for i in sorted(all_ids, key=int) if i not in (a, b)), None)
        self.assertIsNotNone(c, "test setup: expected a third distinct terminal id")
        mutated, n = re.subn(f'terminal2="{b}"', f'terminal2="{c}"', self.text, count=1)
        self.assertEqual(n, 1, "test setup: expected to find the conductor's terminal2 ref")
        p = _write_variant(self.tmp, mutated, "rewired_real_terminal.qet")
        d = canon.diff(canon.canonicalize(SAMPLE), canon.canonicalize(p))
        self.assertTrue(d, "rewiring between two real terminals must produce a canon diff")


class TestCanonTolerance(unittest.TestCase):
    """canon() must not be too strict -- cosmetic-only edits must NOT diff."""

    def setUp(self):
        self.text = SAMPLE.read_text()
        self.tmp = Path("/tmp/claude-1000-canon-test")
        self.tmp.mkdir(exist_ok=True)

    def test_tolerates_timestamp_change(self):
        mutated = self.text.replace('name="saveddate"', 'name="saveddate"').replace(
            "2021-04-17", "1999-01-01"
        )
        p = _write_variant(self.tmp, mutated, "retimestamped.qet")
        d = canon.diff(canon.canonicalize(SAMPLE), canon.canonicalize(p))
        self.assertEqual(d, [], f"a saved-date change should be cosmetic, got: {d}")

    def test_tolerates_conductor_color_change(self):
        mutated, n = re.subn(r'text_color="#000000"', 'text_color="#ff00ff"', self.text)
        self.assertGreater(n, 0, "test setup: expected a text_color attribute")
        p = _write_variant(self.tmp, mutated, "recolored.qet")
        d = canon.diff(canon.canonicalize(SAMPLE), canon.canonicalize(p))
        self.assertEqual(d, [], f"a colour-only change should be cosmetic, got: {d}")

    def test_tolerates_terminal_id_churn(self):
        # table_adr_id is a QHash<Terminal*, int> rebuilt from scratch on
        # every save, so the integer in a terminal's `id` -- and in the
        # conductor terminal1/terminal2 refs that point at it -- churns
        # between processes (FINDINGS.md F004). Renumber every legacy
        # terminal id and its refs by +1000: the wiring is unchanged, so
        # the content-derived identity must report no difference.
        def bump(match):
            return f"{match.group(1)}{int(match.group(2)) + 1000}{match.group(3)}"

        mutated = re.sub(r'(<terminal [^>]*\bid=")(\d+)(")', bump, self.text)
        mutated = re.sub(r'(<conductor [^>]*\bterminal1=")(\d+)(")', bump, mutated)
        mutated = re.sub(r'(<conductor [^>]*\bterminal2=")(\d+)(")', bump, mutated)
        p = _write_variant(self.tmp, mutated, "renumbered_terminals.qet")
        d = canon.diff(canon.canonicalize(SAMPLE), canon.canonicalize(p))
        self.assertEqual(d, [], f"renumbering legacy terminal ids must be cosmetic, got: {d}")

    def test_tolerates_conductor_terminal_order_swap(self):
        # A conductor is electrically symmetric: swapping which terminal is
        # "1" and which is "2" must not be treated as a semantic change.
        m = re.search(r'<conductor ([^>]*)\bterminal1="(\d+)"([^>]*)\bterminal2="(\d+)"', self.text)
        if not m:
            self.skipTest("no conductor with this attribute order in the sample file")
        t1, t2 = m.group(2), m.group(4)
        mutated = self.text.replace(
            f'terminal1="{t1}"', "terminal1=\"__T2__\"", 1
        ).replace(
            f'terminal2="{t2}"', f'terminal2="{t1}"', 1
        ).replace("terminal1=\"__T2__\"", f'terminal1="{t2}"', 1)
        p = _write_variant(self.tmp, mutated, "swapped_terminals.qet")
        d = canon.diff(canon.canonicalize(SAMPLE), canon.canonicalize(p))
        self.assertEqual(d, [], f"swapping terminal1/terminal2 should be cosmetic, got: {d}")


class TestNanInfViolations(unittest.TestCase):
    def setUp(self):
        self.text = SAMPLE.read_text()
        self.tmp = Path("/tmp/claude-1000-canon-test")
        self.tmp.mkdir(exist_ok=True)

    def test_finds_injected_nan(self):
        mutated, n = re.subn(r'(<element [^>]*\bx=")(\d+)(")', r'\1nan\3', self.text, count=1)
        self.assertEqual(n, 1)
        p = _write_variant(self.tmp, mutated, "nan_x.qet")
        v = canon.nan_or_inf_violations(p)
        self.assertTrue(any(x.kind == "nan" for x in v), f"expected a nan violation, got {v}")

    def test_finds_injected_inf(self):
        mutated, n = re.subn(r'(<element [^>]*\by=")(\d+)(")', r'\1inf\3', self.text, count=1)
        self.assertEqual(n, 1)
        p = _write_variant(self.tmp, mutated, "inf_y.qet")
        v = canon.nan_or_inf_violations(p)
        self.assertTrue(any(x.kind == "inf" for x in v), f"expected an inf violation, got {v}")

    def test_clean_real_corpus_has_no_violations(self):
        # This is the check that matters: a NaN/Inf oracle that fires on
        # ordinary shipped example files would be worthless. Sweep all of
        # them, not just the one sample.
        import glob
        offenders = []
        for f in glob.glob("/home/user/qet-fix/examples/*.qet"):
            v = canon.nan_or_inf_violations(Path(f))
            if v:
                offenders.append((f, v))
        self.assertEqual(offenders, [], f"real shipped examples should never contain NaN/Inf: {offenders}")

    def test_malformed_xml_raises_canon_error_not_a_bare_exception(self):
        # Regression: this used to let xml.etree.ElementTree.ParseError
        # propagate uncaught, taking down the whole sweep instead of
        # producing a Finding. Found via a test using a deliberately dumb
        # stand-in binary that copies mutated (possibly malformed) bytes
        # verbatim -- against the real QET binary this was never
        # reachable, since QET itself never produces malformed output.
        p = _write_variant(self.tmp, "<not well formed", "truncated_for_nan_check.qet")
        with self.assertRaises(canon.CanonError):
            canon.nan_or_inf_violations(p)


class TestGridRegressions(unittest.TestCase):
    """
    grid_regressions() is deliberately a BEFORE/AFTER comparison, not an
    absolute "must be on grid" check -- see the rationale in canon.py.
    This is what actually catches the PR #660 bug class: an element that
    was on-grid drifting off-grid across an operation.
    """

    def setUp(self):
        self.text = SAMPLE.read_text()
        self.tmp = Path("/tmp/claude-1000-canon-test")
        self.tmp.mkdir(exist_ok=True)

    def test_flags_an_on_grid_element_pushed_off_grid(self):
        m = re.search(r'<element [^>]*\bx="(\d+)"', self.text)
        self.assertIsNotNone(m)
        x0 = int(m.group(1))
        self.assertEqual(x0 % 10, 0, "test setup expects an on-grid sample element")
        mutated = self.text.replace(f'x="{x0}"', f'x="{x0 + 3}"', 1)
        before = _write_variant(self.tmp, self.text, "grid_before.qet")
        after = _write_variant(self.tmp, mutated, "grid_after.qet")
        regressions = canon.grid_regressions(before, after, grid=10)
        self.assertTrue(regressions, "an on-grid element nudged by 3px must be flagged")

    def test_does_not_flag_a_legitimately_off_grid_element_that_stays_put(self):
        # perceuse.qet has real, legitimate off-grid elements (verified
        # manually: x="488" etc., not a multiple of 10). Comparing it
        # against itself must produce zero regressions -- "already off
        # grid" is not "moved off grid".
        p = Path("/home/user/qet-fix/examples/perceuse.qet")
        regressions = canon.grid_regressions(p, p, grid=10)
        self.assertEqual(regressions, [], "comparing a file to itself must never regress")

    def test_nan_position_does_not_crash_grid_regressions(self):
        # Regression test: simulator/runner.py's sweep found this crashing
        # for real (round(nan / grid) raises ValueError) within the first
        # ~30 mutated inputs. A NaN position must be reported by
        # nan_or_inf_violations(), not crash grid_regressions().
        mutated, n = re.subn(r'(<element [^>]*\bx=")(\d+)(")', r'\1nan\3', self.text, count=1)
        self.assertEqual(n, 1)
        before = _write_variant(self.tmp, self.text, "nan_grid_before.qet")
        after = _write_variant(self.tmp, mutated, "nan_grid_after.qet")
        regressions = canon.grid_regressions(before, after, grid=10)  # must not raise
        self.assertIsInstance(regressions, list)

    def test_real_corpus_pairwise_self_compare_is_clean(self):
        import glob
        offenders = []
        for f in glob.glob("/home/user/qet-fix/examples/*.qet"):
            p = Path(f)
            r = canon.grid_regressions(p, p, grid=10)
            if r:
                offenders.append((f, len(r)))
        self.assertEqual(offenders, [], f"self-comparison must never regress: {offenders}")

    def test_malformed_xml_raises_canon_error_not_a_bare_exception(self):
        good = _write_variant(self.tmp, self.text, "grid_regr_good.qet")
        bad = _write_variant(self.tmp, "<not well formed", "grid_regr_bad.qet")
        with self.assertRaises(canon.CanonError):
            canon.grid_regressions(good, bad)


if __name__ == "__main__":
    unittest.main()
