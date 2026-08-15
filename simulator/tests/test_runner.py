"""
Unit tests for runner.py's non-QET-specific logic: corpus discovery,
health-check quarantine, and deterministic trace replay. Uses a small
synthetic Python script as a stand-in "binary" so quarantine behaviour is
tested without needing a real qelectrotech build -- the sweep against the
real binary is exercised separately (manually, and via
simulator/fixtures/) since it is slow.
"""
import random
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import mutate
from simulator.runner import (RunConfig, _apply_trace_to_bytes,
                               _build_mutated_trace, discover_corpus,
                               health_check_corpus, run_sweep)

# A stand-in for `qelectrotech --resave <in> <out>` that hangs forever if
# the input file's name contains "poison", and otherwise just copies it.
FAKE_BINARY_SCRIPT = textwrap.dedent("""
    import sys, shutil, time
    assert sys.argv[1] == "--resave"
    src, dst = sys.argv[2], sys.argv[3]
    if "poison" in src:
        time.sleep(3600)
    shutil.copy(src, dst)
""")


def _make_fake_binary() -> Path:
    p = Path("/tmp/claude-1000-runner-fakebin.py")
    p.write_text(FAKE_BINARY_SCRIPT)
    return p


class TestDiscoverCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qet-sim-test-discover-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "a.qet").write_text("<project/>")
        (self.tmp / "b.qet").write_text("<project/>")
        (self.tmp / "ignored.txt").write_text("not a project")

    def test_finds_only_qet_files(self):
        found = discover_corpus(self.tmp)
        names = {p.name for p in found}
        self.assertEqual(names, {"a.qet", "b.qet"})

    def test_returns_sorted(self):
        found = discover_corpus(self.tmp)
        self.assertEqual(found, sorted(found))


class TestHealthCheckQuarantine(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qet-sim-test-health-"))
        self.reports = Path(tempfile.mkdtemp(prefix="qet-sim-test-reports-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.reports, ignore_errors=True)
        (self.tmp / "good.qet").write_text("<project/>")
        (self.tmp / "poison_hangs.qet").write_text("<project/>")
        self.fake_bin = _make_fake_binary()

    def test_hanging_seed_is_quarantined_not_used(self):
        cfg = RunConfig(
            binary=sys.executable, corpus_dir=self.tmp, reports_dir=self.reports,
            timeout=1.0,
        )
        seeds = [self.tmp / "good.qet", self.tmp / "poison_hangs.qet"]

        # health_check_corpus calls run_cli(cfg.binary, ["--resave", ...], ...)
        # -- prepend the fake script as the first arg via a wrapper config.
        import simulator.runner as runner_mod
        orig_run_cli = runner_mod.run_cli

        def wrapped_run_cli(binary, args, sandbox, timeout=30.0):
            return orig_run_cli(sys.executable, [str(self.fake_bin), *args], sandbox, timeout=timeout)

        runner_mod.run_cli = wrapped_run_cli
        try:
            health = runner_mod.health_check_corpus(seeds, cfg, self.reports)
        finally:
            runner_mod.run_cli = orig_run_cli

        self.assertEqual(len(health.healthy), 1)
        self.assertEqual(health.healthy[0].name, "good.qet")
        self.assertIn("poison_hangs.qet", health.quarantined)
        self.assertIn("timeout", health.quarantined["poison_hangs.qet"])


class TestSweepMutatorCoverage(unittest.TestCase):
    """
    Regression coverage for a real gap: a sweep report only ever writes a
    line when a finding occurs, so a mutator that is selected but never
    triggers anything is indistinguishable, from the report alone, from a
    mutator that was never selected at all (a real selection bug). This
    was found the hard way -- truncate_bytes had zero occurrences across
    ~500 mutation picks in every prior sweep, which looked exactly like a
    bug until manual checking showed it fires at the expected rate and
    QET just handles truncated input cleanly. run_sweep()'s
    mutator_attempts/mutator_findings counters exist so that question is
    answerable from the summary directly, without a manual investigation.
    """

    def setUp(self):
        self.corpus = Path(tempfile.mkdtemp(prefix="qet-sim-test-coverage-corpus-"))
        self.reports = Path(tempfile.mkdtemp(prefix="qet-sim-test-coverage-reports-"))
        self.addCleanup(shutil.rmtree, self.corpus, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.reports, ignore_errors=True)
        seed = Path("/home/user/qet-fix/examples/741.qet")
        shutil.copy(seed, self.corpus / "741.qet")

        # Always-clean fake binary: never crashes, never finds anything,
        # regardless of what mutation was applied. Isolates "does the
        # counter correctly tally every attempt" from "does QET crash",
        # which is exercised for real elsewhere (fixture_known_bugs.py).
        script = Path(tempfile.mkdtemp(prefix="qet-sim-test-coverage-bin-")) / "fakebin"
        script.write_text(textwrap.dedent(f"""\
            #!{sys.executable}
            import sys, shutil
            assert sys.argv[1] == "--resave"
            shutil.copy(sys.argv[2], sys.argv[3])
        """))
        script.chmod(0o755)
        self.addCleanup(shutil.rmtree, script.parent, ignore_errors=True)
        self.fake_binary = script

    def test_every_attempted_mutator_is_counted_even_with_no_findings(self):
        from simulator.runner import RunConfig, run_sweep

        cfg = RunConfig(
            binary=str(self.fake_binary), corpus_dir=self.corpus, reports_dir=self.reports,
            iterations=40, chain_length=1, timeout=5.0, master_seed=1,
        )
        summary = run_sweep(cfg)

        # The fake binary is a blind byte-copy: it never crashes, and it
        # never diverges between resave1 and resave2 (same bytes copied
        # twice). It CAN still legitimately produce O2/O3/O6 "could not
        # parse" findings when a mutator hands it malformed bytes it just
        # passes through unmodified -- that is the oracles' own existing,
        # correct CanonError handling doing its job, not something this
        # test should assert away. What genuinely must hold for a binary
        # that never crashes is exactly that: no crashes.
        self.assertEqual(summary["crashes"], 0)
        self.assertNotIn("O1", summary["findings_by_oracle"])
        # Attempts must still be tallied for every mutator that was
        # actually selected across 40 iterations. With 8 mutators and 40
        # draws, expecting literally zero attempts for any one mutator is
        # implausible (~(7/8)^40 ~= 0.5% per mutator) without it being a
        # real selection gap.
        total_attempts = sum(summary["mutator_attempts"].values())
        self.assertEqual(total_attempts, 40, "chain_length=1 means exactly one mutator per iteration")
        never_attempted = [name for name, n in summary["mutator_attempts"].items() if n == 0]
        self.assertEqual(never_attempted, [],
                          f"mutator(s) never selected across 40 draws -- check selection logic: {never_attempted}")


class TestBuildAndReplayTrace(unittest.TestCase):
    def test_replayed_trace_reproduces_identical_bytes(self):
        seed = Path("/home/user/qet-fix/examples/741.qet")
        seed_bytes = seed.read_bytes()
        tmp = Path(tempfile.mkdtemp(prefix="qet-sim-test-replay-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        cfg = RunConfig(binary="unused", corpus_dir=tmp, reports_dir=tmp,
                         chain_length=3, mutator_names=list(mutate.ALL_MUTATOR_NAMES))
        rng = random.Random(2024)
        trace = _build_mutated_trace(seed, seed_bytes, cfg, rng)
        first = _apply_trace_to_bytes(trace, seed_bytes)
        second = _apply_trace_to_bytes(trace, seed_bytes)
        self.assertEqual(first, second, "replaying the same trace twice must be byte-identical")
        self.assertGreaterEqual(len(trace.steps), 1)


class TestFirstRunWithAbsentReportsDir(unittest.TestCase):
    """
    Regression for the fresh-clone bug: run_sweep created sandboxes under
    reports_dir (via health_check_corpus) BEFORE creating reports_dir
    itself. reports/ is gitignored, so on a fresh checkout the very first
    `sweep` run raised FileNotFoundError before a single iteration.
    """

    def test_sweep_creates_reports_dir_and_runs(self):
        tmp = Path(tempfile.mkdtemp(prefix="qet-sim-test-firstrun-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corpus = tmp / "corpus"
        corpus.mkdir()
        (corpus / "seed.qet").write_text(
            '<project><diagram order="0"><element uuid="{00000000-0000-0000-0000-000000000001}"'
            ' x="10" y="10"/></diagram></project>')
        reports = tmp / "reports-does-not-exist"

        # Deterministic byte-copy fake binary (same pattern as
        # TestSweepMutatorCoverage): never crashes, never diverges.
        script = tmp / "fakebin"
        script.write_text(textwrap.dedent(f"""\
            #!{sys.executable}
            import sys, shutil
            assert sys.argv[1] == "--resave"
            shutil.copy(sys.argv[2], sys.argv[3])
        """))
        script.chmod(0o755)

        cfg = RunConfig(binary=str(script), corpus_dir=corpus, reports_dir=reports,
                        iterations=2, timeout=5.0, master_seed=1)
        summary = run_sweep(cfg)

        self.assertTrue(reports.exists(), "run_sweep must create reports_dir itself")
        self.assertEqual(summary["iterations"], 2)
        self.assertTrue(summary["o9_deterministic"],
                        "byte-copy fake binary is deterministic, so the O9 self-check must pass")


class TestO9SelfCheck(unittest.TestCase):
    """
    O9 (SIMULATOR-DESIGN.md §3, "check this first, on every run") is wired
    into every sweep: identical input must produce identical canonical
    output, checked before any iteration result is trusted.
    """

    def test_nondeterministic_binary_is_flagged(self):
        tmp = Path(tempfile.mkdtemp(prefix="qet-sim-test-o9-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corpus = tmp / "corpus"
        corpus.mkdir()
        (corpus / "seed.qet").write_text(
            '<project><diagram order="0"><element uuid="{00000000-0000-0000-0000-000000000001}"'
            ' x="10" y="10"/></diagram></project>')

        # A fake binary whose resave output depends on an external counter:
        # every invocation injects a new unique uuid, so two runs on
        # identical input diverge -- exactly what O9 must catch.
        counter = tmp / "counter.txt"
        script = tmp / "nondetbin"
        script.write_text(textwrap.dedent(f"""\
            #!{sys.executable}
            import sys, pathlib
            assert sys.argv[1] == "--resave"
            counter = pathlib.Path({str(counter)!r})
            n = int(counter.read_text()) if counter.exists() else 0
            counter.write_text(str(n + 1))
            src = pathlib.Path(sys.argv[2]).read_bytes()
            injected = (b'<element uuid="{{00000000-0000-0000-0000-0000000000%02d}}"'
                        b' x="1" y="1"/>' % n)
            out = sys.argv[3]
            with open(out, "wb") as f:
                f.write(src.replace(b"</project>", injected + b"</project>"))
        """))
        script.chmod(0o755)

        cfg = RunConfig(binary=str(script), corpus_dir=corpus, reports_dir=tmp / "reports",
                        iterations=1, timeout=5.0, master_seed=1)
        summary = run_sweep(cfg)

        self.assertFalse(summary["o9_deterministic"],
                         "identical input produced different canonical output -- O9 must fail")
        self.assertIn("O9", summary["findings_by_oracle"])


if __name__ == "__main__":
    unittest.main()
