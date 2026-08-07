"""Unit tests for mutate.py -- no binary needed."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import mutate

SAMPLE = Path("/home/user/qet-fix/examples/741.qet")


class TestTextMutators(unittest.TestCase):
    def setUp(self):
        self.data = SAMPLE.read_bytes()
        self.rng = random.Random(12345)

    def test_all_text_mutators_apply_and_produce_resolved_args(self):
        for name in mutate.TEXT_MUTATORS:
            with self.subTest(mutator=name):
                result = mutate.apply_named(name, self.data, random.Random(1))
                self.assertIsNotNone(result, f"{name} should apply to a real project file")
                self.assertIsInstance(result.args, dict)
                self.assertIn("kind", result.args)
                self.assertEqual(result.args["kind"], name)
                self.assertNotEqual(result.data, self.data, f"{name} should actually change the bytes")

    def test_drop_element_block_removes_a_uuid(self):
        result = mutate.apply_named("drop_element_block", self.data, self.rng)
        self.assertIsNotNone(result)
        removed = result.args["removed_uuid"]
        self.assertIsNotNone(removed)
        self.assertNotIn(removed, result.text)

    def test_corrupt_uuid_char_changes_exactly_one_char(self):
        result = mutate.apply_named("corrupt_uuid_char", self.data, self.rng)
        self.assertIsNotNone(result)
        orig, corrupt = result.args["original_uuid"], result.args["corrupted_uuid"]
        diffs = sum(1 for a, b in zip(orig, corrupt) if a != b)
        self.assertEqual(diffs, 1, f"expected exactly one char changed: {orig} -> {corrupt}")
        self.assertIn(corrupt, result.text)
        self.assertNotIn(orig, result.text)

    def test_inject_nan_coordinate_is_present_in_output(self):
        result = mutate.apply_named("inject_nan_coordinate", self.data, self.rng)
        self.assertIsNotNone(result)
        self.assertIn(f'{result.args["attribute"]}="nan"', result.text)

    def test_reproducibility_same_rng_state_same_result(self):
        r1 = mutate.apply_named("corrupt_uuid_char", self.data, random.Random(42))
        r2 = mutate.apply_named("corrupt_uuid_char", self.data, random.Random(42))
        self.assertEqual(r1.args, r2.args)
        self.assertEqual(r1.data, r2.data)

    def test_apply_resolved_replays_every_text_mutator_exactly(self):
        # This is the property the whole trace/replay system in trace.py
        # depends on: apply_resolved(args, seed) must reproduce
        # apply_named()'s output with NO randomness involved.
        for name in mutate.TEXT_MUTATORS:
            with self.subTest(mutator=name):
                original = mutate.apply_named(name, self.data, random.Random(7))
                self.assertIsNotNone(original)
                replayed = mutate.apply_resolved(original.args, self.data)
                self.assertEqual(replayed, original.data,
                                  f"{name}: replay diverged from the original mutation")


class TestByteMutators(unittest.TestCase):
    def setUp(self):
        self.data = SAMPLE.read_bytes()
        self.rng = random.Random(999)

    def test_truncate_produces_shorter_file(self):
        result = mutate.apply_named("truncate_bytes", self.data, self.rng)
        self.assertLess(len(result.data), len(self.data))
        self.assertEqual(len(result.data), result.args["offset"])

    def test_flip_random_bit_changes_exactly_one_bit(self):
        result = mutate.apply_named("flip_random_bit", self.data, self.rng)
        self.assertEqual(len(result.data), len(self.data))
        diff_positions = [i for i in range(len(self.data)) if self.data[i] != result.data[i]]
        self.assertEqual(len(diff_positions), 1)
        off = result.args["byte_offset"]
        self.assertEqual(diff_positions[0], off)
        # exactly one bit differs at that byte
        xor = self.data[off] ^ result.data[off]
        self.assertEqual(bin(xor).count("1"), 1)

    def test_truncate_empty_input_does_not_crash(self):
        result = mutate.apply_named("truncate_bytes", b"", self.rng)
        self.assertEqual(result.data, b"")

    def test_flip_empty_input_does_not_crash(self):
        result = mutate.apply_named("flip_random_bit", b"", self.rng)
        self.assertEqual(result.data, b"")

    def test_apply_resolved_replays_byte_mutators_exactly(self):
        for name in mutate.BYTE_MUTATORS:
            with self.subTest(mutator=name):
                original = mutate.apply_named(name, self.data, random.Random(3))
                replayed = mutate.apply_resolved(original.args, self.data)
                self.assertEqual(replayed, original.data, f"{name}: replay diverged")


class TestPathologicalTitleblock(unittest.TestCase):
    def test_covers_the_designed_boundary_family(self):
        cases = mutate.pathological_titleblock_columns()
        sums = [c["sum"] for c in cases]
        # The exact family SIMULATOR-DESIGN.md §5.1 calls for.
        for expected in (0, 100, 101):
            self.assertIn(expected, sums, f"boundary case sum={expected} missing")

    def test_zero_sum_has_empty_cols(self):
        cases = mutate.pathological_titleblock_columns([0])
        self.assertEqual(cases[0]["cols"], "")

    def test_hundred_sum_cols_actually_sum_to_100(self):
        cases = mutate.pathological_titleblock_columns([100])
        cols = cases[0]["cols"]
        parts = [int(p[1:-1]) for p in cols.split(";") if p]
        self.assertEqual(sum(parts), 100)


if __name__ == "__main__":
    unittest.main()
