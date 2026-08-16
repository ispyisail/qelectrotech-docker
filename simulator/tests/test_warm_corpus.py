"""
Unit tests for warm_corpus() (W1 brief §2a/§2b) -- no real qelectrotech build
needed. The "binary" is a small Python stand-in that mimics the one behaviour
warming exists to absorb: QET assigns a uuid to a legacy <conductor> that lacks
one on first load, and is stable from the second save on (W1 brief §1).

Why a fake migration binary and not the real one: the real master binary's
resave is NOT idempotent on legacy conductor files -- not because of the uuid
migration, but because of the separate, real `Diagram::toXml` terminal-id
churn (pointer-keyed `table_adr_id`) that warming cannot fix. That defect is
documented in tests/determinism/check.py and reported out-of-band; it is NOT
something a harness can warm away, so these tests assert the property warming
is actually responsible for: once a file has been resaved once, a second warm
is a canonical no-op given a binary whose first-save migration is the only
source of churn.
"""
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import canon
from simulator.runner import warm_corpus

# A minimal .qet whose single conductor lacks a uuid -- exactly the legacy
# shape the migration described in the W1 brief acts on.
FIXTURE = """\
<project>
  <diagram order="0">
    <conductors>
      <conductor terminal1="t1" terminal2="t2"/>
    </conductors>
  </diagram>
</project>
"""

# Stand-in binary: on --resave, give the first uuid-less <conductor> a fixed
# uuid; leave everything else untouched. Idempotent by construction (the
# second resave sees the uuid already present), like QET's migration.
FAKE_MIGRATION_BINARY = textwrap.dedent("""\
    #!{python}
    import pathlib, re, sys
    assert sys.argv[1] == "--resave"
    src, dst = sys.argv[2], sys.argv[3]
    text = pathlib.Path(src).read_text()
    if "poison" in src:
        import time; time.sleep(3600)
    m = re.search(r"<conductor\\b[^>]*>", text)
    if m and "uuid=" not in m.group(0):
        tag = m.group(0)
        if tag.endswith("/>"):
            newtag = tag[:-2] + ' uuid="{{11111111-1111-1111-1111-111111111111}}"/>'
        else:
            newtag = tag[:-1] + ' uuid="{{11111111-1111-1111-1111-111111111111}}">'
        text = text[:m.start()] + newtag + text[m.end():]
    pathlib.Path(dst).write_text(text)
""")


def _write_binary(dir_: Path) -> Path:
    """Write the fake migration binary and return its path."""
    bin_ = dir_ / "fakebin"
    bin_.write_text(FAKE_MIGRATION_BINARY.format(python=sys.executable))
    bin_.chmod(0o755)
    return bin_


class TestWarmCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qet-sim-test-warm-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.binary = _write_binary(self.tmp)

    def _corpus(self, files: dict[str, str]) -> Path:
        corpus = self.tmp / "corpus"
        corpus.mkdir()
        for name, content in files.items():
            (corpus / name).write_text(content)
        return corpus

    def test_warming_is_idempotent(self):
        """warm(warm(x)) canon-equals warm(x) -- the property W1 §2b names."""
        corpus = self._corpus({"fixture.qet": FIXTURE})
        out1 = self.tmp / "warm1"
        out2 = self.tmp / "warm2"

        warm_corpus(str(self.binary), corpus, out1, timeout=5.0)
        warm_corpus(str(self.binary), out1, out2, timeout=5.0)

        c1 = canon.canonicalize(out1 / "fixture.qet")
        c2 = canon.canonicalize(out2 / "fixture.qet")
        self.assertTrue(canon.canon_equal(c1, c2),
                        f"warm(warm(x)) != warm(x): {canon.diff(c1, c2)}")

    def test_first_warm_actually_applies_the_migration(self):
        """Guard that the fixture + fake binary do what the test assumes:
        the first warm injects the conductor uuid, so the idempotence test is
        not passing vacuously on an empty transformation."""
        corpus = self._corpus({"fixture.qet": FIXTURE})
        out = self.tmp / "warm1"
        warm_corpus(str(self.binary), corpus, out, timeout=5.0)
        warmed = canon.canonicalize(out / "fixture.qet")
        self.assertIn("{11111111-1111-1111-1111-111111111111}", warmed.uuid_universe,
                      "fake binary should have assigned a conductor uuid on first warm")

    def test_warm_writes_output_and_provenance(self):
        corpus = self._corpus({"a.qet": FIXTURE, "b.qet": FIXTURE})
        out = self.tmp / "warm"
        summary = warm_corpus(str(self.binary), corpus, out, timeout=5.0)

        self.assertEqual(sorted(summary["warmed"]), ["a.qet", "b.qet"])
        self.assertEqual(summary["skipped"], {})
        self.assertEqual(summary["corpus_size"], 2)
        self.assertTrue((out / "a.qet").exists())
        self.assertTrue((out / "b.qet").exists())

        provenance = (out / "WARMED_FROM.txt").read_text()
        self.assertIn(f"source_dir: {corpus.resolve()}", provenance)
        self.assertIn(f"binary: {self.binary.resolve()}", provenance)
        self.assertIn("binary_describe:", provenance)

    def test_warm_skips_crashing_file_nonfatally(self):
        corpus = self._corpus({"good.qet": FIXTURE, "poison_hangs.qet": FIXTURE})
        out = self.tmp / "warm"
        summary = warm_corpus(str(self.binary), corpus, out, timeout=1.0)

        self.assertEqual(summary["warmed"], ["good.qet"])
        self.assertIn("poison_hangs.qet", summary["skipped"])
        self.assertIn("timeout", summary["skipped"]["poison_hangs.qet"])
        self.assertTrue((out / "good.qet").exists())
        self.assertFalse((out / "poison_hangs.qet").exists())

    def test_warm_refuses_to_overwrite_source_corpus(self):
        corpus = self._corpus({"a.qet": FIXTURE})
        with self.assertRaises(RuntimeError):
            warm_corpus(str(self.binary), corpus, corpus, timeout=5.0)


if __name__ == "__main__":
    unittest.main()
