"""Fail-fast skip for projects that cannot be loaded by either ref.

examples/schema_indus.qet is version 0.3 and raises a modal during load that no
offscreen process can dismiss, so every verb burns the full timeout. It cost
~20 of every sweep's ~23 minutes.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.refdiff.__main__ import is_unloadable


class TestIsUnloadable(unittest.TestCase):
    def test_first_verb_timing_out_on_both_refs_skips_the_rest(self):
        self.assertTrue(is_unloadable(0, True, True))

    def test_timeout_on_base_only_is_never_skipped(self):
        """head fixing a hang is an improvement -- must still be measured."""
        self.assertFalse(is_unloadable(0, True, False))

    def test_timeout_on_head_only_is_never_skipped(self):
        """head hanging where base did not is THE regression signal."""
        self.assertFalse(is_unloadable(0, False, True))

    def test_no_timeout_does_not_skip(self):
        self.assertFalse(is_unloadable(0, False, False))

    def test_later_verb_timing_out_does_not_skip(self):
        """A verb-specific hang is not the same as an unloadable project, so
        only the first verb may trigger the skip."""
        for vi in (1, 2, 3, 4):
            self.assertFalse(is_unloadable(vi, True, True), f"verb index {vi}")

    def test_no_fail_fast_disables_it_entirely(self):
        self.assertFalse(is_unloadable(0, True, True, fail_fast=False))


if __name__ == "__main__":
    unittest.main()
