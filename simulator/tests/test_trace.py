"""Unit tests for trace.py -- serialization and sub_trace renumbering."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator.trace import Step, Trace


class TestStep(unittest.TestCase):
    def test_round_trip(self):
        s = Step(seq=3, op="mutate.flip_random_bit", args={"byte_offset": 12, "bit": 4}, note="hi")
        d = s.to_dict()
        s2 = Step.from_dict(d)
        self.assertEqual(s2.seq, s.seq)
        self.assertEqual(s2.op, s.op)
        self.assertEqual(s2.args, s.args)
        self.assertEqual(s2.note, s.note)

    def test_default_note_is_empty(self):
        s = Step.from_dict({"seq": 0, "op": "x", "args": {}})
        self.assertEqual(s.note, "")


class TestTrace(unittest.TestCase):
    def test_append_assigns_sequential_seq(self):
        t = Trace(seed_name="f.qet", seed_sha256="a" * 64, seed=1)
        s0 = t.append("op1", {"a": 1})
        s1 = t.append("op2", {"b": 2})
        self.assertEqual(s0.seq, 0)
        self.assertEqual(s1.seq, 1)
        self.assertEqual(len(t.steps), 2)

    def test_save_and_load_round_trip(self):
        t = Trace(seed_name="f.qet", seed_sha256="b" * 64, seed=42, meta={"k": "v"})
        t.append("mutate.drop_element_block", {"removed_uuid": "{x}"})
        t.append("mutate.flip_random_bit", {"byte_offset": 5, "bit": 2})

        tmp = Path("/tmp/claude-1000-trace-test.json")
        t.save(tmp)
        loaded = Trace.load(tmp)

        self.assertEqual(loaded.seed_name, t.seed_name)
        self.assertEqual(loaded.seed_sha256, t.seed_sha256)
        self.assertEqual(loaded.seed, t.seed)
        self.assertEqual(loaded.meta, t.meta)
        self.assertEqual(len(loaded.steps), 2)
        self.assertEqual([s.op for s in loaded.steps], [s.op for s in t.steps])
        self.assertEqual([s.args for s in loaded.steps], [s.args for s in t.steps])

    def test_saved_file_is_valid_json(self):
        t = Trace(seed_name="f.qet", seed_sha256="c" * 64, seed=0)
        t.append("op", {"x": 1})
        tmp = Path("/tmp/claude-1000-trace-test2.json")
        t.save(tmp)
        json.loads(tmp.read_text())  # must not raise

    def test_sub_trace_renumbers_from_zero(self):
        t = Trace(seed_name="f.qet", seed_sha256="d" * 64, seed=0)
        for i in range(5):
            t.append("op", {"i": i})
        sub = t.sub_trace([1, 3])
        self.assertEqual([s.seq for s in sub.steps], [0, 1])
        self.assertEqual([s.args["i"] for s in sub.steps], [1, 3])

    def test_sub_trace_preserves_seed_identity(self):
        t = Trace(seed_name="f.qet", seed_sha256="e" * 64, seed=99)
        t.append("op", {})
        sub = t.sub_trace([0])
        self.assertEqual(sub.seed_name, t.seed_name)
        self.assertEqual(sub.seed_sha256, t.seed_sha256)
        self.assertEqual(sub.seed, t.seed)

    def test_sub_trace_records_shrink_provenance(self):
        t = Trace(seed_name="f.qet", seed_sha256="f" * 64, seed=0)
        for i in range(10):
            t.append("op", {"i": i})
        sub = t.sub_trace([2, 5])
        self.assertEqual(sub.meta.get("shrunk_from"), 10)

    def test_empty_sub_trace(self):
        t = Trace(seed_name="f.qet", seed_sha256="0" * 64, seed=0)
        t.append("op", {})
        sub = t.sub_trace([])
        self.assertEqual(len(sub.steps), 0)


if __name__ == "__main__":
    unittest.main()
