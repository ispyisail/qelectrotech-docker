"""
Unit tests for tools/abdiff/compare.py -- pure classification logic, no
qelectrotech binary needed. The two tests that matter most mirror
LAB-PLAN.md L1's proof fixtures directly:

  - test_timeout_on_one_side_is_a_only_fails_not_same: the exact failure
    mode the task warns about -- "a harness that hangs waiting for
    variant A, or that reports 'no output from either' and calls them
    equal, has failed the fixture."
  - test_identical_success_is_same: same-vs-same must report `same`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from simulator.proc import Outcome
from tools.abdiff import compare


def _outcome(**kw) -> Outcome:
    defaults = dict(
        argv=["qelectrotech", "--info", "x.qet"],
        returncode=0,
        signal=None,
        stdout="",
        stderr="",
        wall_seconds=1.0,
        timed_out=False,
        sandbox_root="/tmp/qet-sim-abc123",
    )
    defaults.update(kw)
    return Outcome(**defaults).classify()


class TestFailureClassification(unittest.TestCase):
    def test_timeout_on_one_side_is_a_only_fails_not_same(self):
        a = _outcome(returncode=None, timed_out=True, wall_seconds=60.0)
        b = _outcome(returncode=0, stdout='{"ok": true}\n')
        result = compare.compare(["--info", "x.qet"], a, b, Path("/tmp/nope-a"), Path("/tmp/nope-b"))
        self.assertEqual(result.verdict, compare.VERDICT_A_ONLY_FAILS)
        self.assertTrue(result.a_failed)
        self.assertFalse(result.b_failed)
        self.assertNotEqual(result.verdict, compare.VERDICT_SAME)

    def test_timeout_on_b_side_is_b_only_fails(self):
        a = _outcome(returncode=0)
        b = _outcome(returncode=None, timed_out=True, wall_seconds=60.0)
        result = compare.compare(["--info", "x.qet"], a, b, Path("/tmp/nope-a"), Path("/tmp/nope-b"))
        self.assertEqual(result.verdict, compare.VERDICT_B_ONLY_FAILS)

    def test_both_timeout_the_same_way_is_same(self):
        a = _outcome(returncode=None, timed_out=True, wall_seconds=60.0)
        b = _outcome(returncode=None, timed_out=True, wall_seconds=60.3)
        result = compare.compare(["--info", "x.qet"], a, b, Path("/tmp/nope-a"), Path("/tmp/nope-b"))
        self.assertEqual(result.verdict, compare.VERDICT_SAME)

    def test_signal_crash_on_one_side_is_a_only_fails(self):
        a = _outcome(returncode=-11)
        b = _outcome(returncode=0)
        result = compare.compare(["--check-elements", "x"], a, b, Path("/tmp/nope-a"), Path("/tmp/nope-b"))
        self.assertEqual(result.verdict, compare.VERDICT_A_ONLY_FAILS)


class TestSuccessComparison(unittest.TestCase):
    def test_identical_success_is_same(self, tmp=None):
        import tempfile
        with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
            a = _outcome(returncode=0, stdout='{"elements": 3}\n')
            b = _outcome(returncode=0, stdout='{"elements": 3}\n')
            result = compare.compare(["--info", "x.qet"], a, b, Path(da), Path(db))
            self.assertEqual(result.verdict, compare.VERDICT_SAME)
            self.assertEqual(result.reasons, [])

    def test_different_stdout_is_differs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
            a = _outcome(returncode=0, stdout='{"elements": 3}\n')
            b = _outcome(returncode=0, stdout='{"elements": 4}\n')
            result = compare.compare(["--info", "x.qet"], a, b, Path(da), Path(db))
            self.assertEqual(result.verdict, compare.VERDICT_DIFFERS)
            self.assertTrue(any("stdout differs" in r for r in result.reasons))

    def test_sandbox_root_noise_is_normalized_away(self):
        import tempfile
        with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
            a = _outcome(returncode=0, stdout="wrote /tmp/qet-sim-AAA/work/out.qet\n",
                         sandbox_root="/tmp/qet-sim-AAA")
            b = _outcome(returncode=0, stdout="wrote /tmp/qet-sim-BBB/work/out.qet\n",
                         sandbox_root="/tmp/qet-sim-BBB")
            result = compare.compare(["--resave", "x.qet", "out.qet"], a, b, Path(da), Path(db))
            self.assertEqual(result.verdict, compare.VERDICT_SAME)

    def test_export_wires_empty_result_on_both_sides_is_not_a_failure(self):
        import tempfile
        with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
            a = _outcome(returncode=1, stderr="Nothing to export (empty list).\n")
            b = _outcome(returncode=1, stderr="Nothing to export (empty list).\n")
            result = compare.compare(["--export-wires", "x.qet", "out.csv"], a, b, Path(da), Path(db))
            self.assertFalse(result.a_failed)
            self.assertFalse(result.b_failed)
            self.assertEqual(result.verdict, compare.VERDICT_SAME)

    def test_produced_file_byte_diff_is_detected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
            (Path(da) / "out.csv").write_text("a;b\n1;2\n")
            (Path(db) / "out.csv").write_text("a;b\n1;3\n")
            a = _outcome(returncode=0)
            b = _outcome(returncode=0)
            result = compare.compare(["--export-bom", "x.qet", "out.csv"], a, b, Path(da), Path(db))
            self.assertEqual(result.verdict, compare.VERDICT_DIFFERS)
            self.assertTrue(any("out.csv differs" in r for r in result.reasons))

    def test_qet_load_timing_noise_is_normalized_away(self):
        # qetproject.cpp's qInfo() load timers write per-run wall-clock
        # timings to stderr. Two runs of the SAME binary differ only in
        # these numbers, so a same-vs-same --info run must still be `same`
        # (this was the first real bug the harness produced -- it reported
        # `differs` on --a master --b master).
        import tempfile
        with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
            a = _outcome(returncode=0, stderr=(
                'SQLite version:  "3.46.1"\n'
                "Project content built in 1.8 seconds (elements collection 0.019, diagrams 1.709, terminal strips 0, refresh 0.018, database 0.054)\n"
                'Project "perceuse.qet" (1763 KiB) opened in 1.913 seconds (xml parsing 0.109, content 1.804)\n'
            ))
            b = _outcome(returncode=0, stderr=(
                'SQLite version:  "3.46.1"\n'
                "Project content built in 1.83 seconds (elements collection 0.017, diagrams 1.73, terminal strips 0, refresh 0.019, database 0.064)\n"
                'Project "perceuse.qet" (1763 KiB) opened in 1.929 seconds (xml parsing 0.095, content 1.834)\n'
            ))
            result = compare.compare(["--info", "x.qet"], a, b, Path(da), Path(db))
            self.assertEqual(result.verdict, compare.VERDICT_SAME)
            self.assertEqual(result.reasons, [])

    def test_qdebug_pointer_address_noise_is_normalized_away(self):
        # qDebug() prints live QObject pointers as ClassName(0x...); the
        # address is an ASLR heap address that differs every run. A
        # master-vs-master --resave was reporting DIFFERS solely because
        #   "exporting diagram \"...\"" [ Diagram(0x55e51b6a15a0) ]
        # changed address between runs. It must not.
        import tempfile
        with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
            a = _outcome(returncode=0, stderr=(
                'Export XML de 1 schemas\n'
                '"exporting diagram \\"Operational amplifier uA741\\""'
                ' [ Diagram(0x55e51b6a15a0) ]\n'
            ))
            b = _outcome(returncode=0, stderr=(
                'Export XML de 1 schemas\n'
                '"exporting diagram \\"Operational amplifier uA741\\""'
                ' [ Diagram(0x61db43a1c6c0) ]\n'
            ))
            result = compare.compare(["--resave", "x.qet", "out.qet"], a, b, Path(da), Path(db))
            self.assertEqual(result.verdict, compare.VERDICT_SAME)
            self.assertEqual(result.reasons, [])

    def test_qdebug_pointer_noise_does_not_mask_real_stderr_diff(self):
        import tempfile
        with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
            a = _outcome(returncode=0, stderr='[ Diagram(0x55e51b6a15a0) ]\n')
            b = _outcome(returncode=0, stderr='[ Diagram(0x61db43a1c6c0) ]\nSomething actually different\n')
            result = compare.compare(["--resave", "x.qet", "out.qet"], a, b, Path(da), Path(db))
            self.assertEqual(result.verdict, compare.VERDICT_DIFFERS)

    def test_qet_load_timing_noise_does_not_mask_real_stderr_diff(self):
        import tempfile
        with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
            a = _outcome(returncode=0, stderr="SQLite version:  \"3.46.1\"\n")
            b = _outcome(returncode=0, stderr="SQLite version:  \"3.46.1\"\nSomething actually different\n")
            result = compare.compare(["--info", "x.qet"], a, b, Path(da), Path(db))
            self.assertEqual(result.verdict, compare.VERDICT_DIFFERS)


if __name__ == "__main__":
    unittest.main()
