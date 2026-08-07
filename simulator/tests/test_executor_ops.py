"""
Unit tests for executor_ops.py's plumbing (JSON summary parsing, ops file
writing) using a fake stand-in binary -- does not need a --test-ops-capable
qelectrotech build. The real thing is exercised by
fixtures/fixture_element_info_orphan.py, which does need one.
"""
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import env
from simulator.executor_ops import first_element_uuid, run_ops

SAMPLE = Path("/home/user/qet-fix/examples/741.qet")

# Stand-in --test-ops: verifies argv shape, echoes the ops file back as
# proof they were written correctly, and copies the input as output.
FAKE_TESTOPS_SCRIPT = textwrap.dedent("""
    import sys, shutil, json
    assert sys.argv[1] == "--test-ops"
    project, ops_path, output = sys.argv[2], sys.argv[3], sys.argv[4]
    ops = json.loads(open(ops_path).read())
    shutil.copy(project, output)
    print(json.dumps({"ops_applied": len(ops), "element_count": 65, "element_info_count": 65}))
""")


def _make_fake_binary() -> Path:
    p = Path(tempfile.mkdtemp(prefix="qet-sim-test-testops-")) / "fakebin"
    p.write_text(f"#!{sys.executable}\n{FAKE_TESTOPS_SCRIPT}")
    p.chmod(0o755)
    return p


class TestRunOps(unittest.TestCase):
    def setUp(self):
        self.fake_binary = _make_fake_binary()
        self.addCleanup(shutil.rmtree, self.fake_binary.parent, ignore_errors=True)

    def test_writes_ops_and_parses_summary(self):
        # Assertions on output_path deliberately stay INSIDE the `with`:
        # sandbox_context() deletes the sandbox (and everything in it,
        # including the output file) on __exit__, so checking
        # output_path.exists() after the block always sees it already
        # gone -- caught this exact ordering mistake here first.
        ops = [{"op": "select", "uuids": ["{x}"]}, {"op": "delete"}]
        with env.sandbox_context() as sb:
            outcome, output_path, summary = run_ops(str(self.fake_binary), SAMPLE, ops, sb)
            self.assertFalse(outcome.crashed)
            self.assertIsNotNone(summary)
            self.assertEqual(summary["ops_applied"], 2)
            self.assertTrue(output_path.exists())

    def test_summary_is_none_when_binary_produces_no_json(self):
        script = Path(tempfile.mkdtemp(prefix="qet-sim-test-nojson-")) / "fakebin"
        script.write_text(f"#!{sys.executable}\nimport sys; sys.exit(1)\n")
        script.chmod(0o755)
        self.addCleanup(shutil.rmtree, script.parent, ignore_errors=True)

        with env.sandbox_context() as sb:
            outcome, _, summary = run_ops(str(script), SAMPLE, [{"op": "delete"}], sb)
        self.assertIsNone(summary)
        self.assertFalse(outcome.crashed)  # exit 1 is a clean failure, not a crash


class TestFirstElementUuid(unittest.TestCase):
    def test_finds_a_real_uuid_in_a_real_project(self):
        uuid = first_element_uuid(SAMPLE)
        self.assertIsNotNone(uuid)
        self.assertTrue(uuid.startswith("{") and uuid.endswith("}"))

    def test_empty_project_returns_none(self):
        tmp = Path(tempfile.mkdtemp(prefix="qet-sim-test-empty-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        empty = tmp / "empty.qet"
        empty.write_text('<project version="0.90"><newdiagrams/></project>')
        self.assertIsNone(first_element_uuid(empty))


if __name__ == "__main__":
    unittest.main()
