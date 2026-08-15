"""Unit tests for __main__.py's command handlers -- no binary needed."""
import argparse
import hashlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import __main__ as sim_main
from simulator import mutate
from simulator.trace import Trace


class TestCmdReplay(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qet-sim-test-main-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        corpus = self.tmp / "corpus"
        corpus.mkdir()
        self.seed = corpus / "seed.qet"
        self.seed.write_text("<project/>")
        self.trace = self.tmp / "trace.json"
        Trace(seed_name="seed.qet",
              seed_sha256=hashlib.sha256(self.seed.read_bytes()).hexdigest(),
              seed=0).save(self.trace)
        self.args = argparse.Namespace(binary="/usr/bin/false",
                                       corpus=corpus, trace=self.trace)

    def test_replay_checks_for_live_instance_like_sweep_and_fixtures(self):
        with mock.patch("simulator.env.assert_no_other_qet_running") as guard, \
             mock.patch("simulator.__main__._apply_trace_to_bytes",
                        return_value=b"<project/>"), \
             mock.patch("simulator.__main__._execute_and_check", return_value=[]), \
             mock.patch("sys.stdout", io.StringIO()):
            rc = sim_main.cmd_replay(self.args)
        guard.assert_called_once_with("/usr/bin/false")
        self.assertEqual(rc, 0)

    def test_replay_error_is_a_clean_exit_not_a_traceback(self):
        stderr = io.StringIO()
        with mock.patch("simulator.env.assert_no_other_qet_running"), \
             mock.patch("simulator.__main__._apply_trace_to_bytes",
                        side_effect=mutate.ReplayError("seed changed")), \
             mock.patch("sys.stderr", stderr):
            rc = sim_main.cmd_replay(self.args)
        self.assertEqual(rc, 2)
        self.assertIn("cannot replay trace", stderr.getvalue())
        self.assertIn("seed changed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
