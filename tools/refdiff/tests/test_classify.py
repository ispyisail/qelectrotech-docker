"""
Unit tests for tools.refdiff.classify and tools.refdiff.normalize -- pure
logic, no qelectrotech binary needed.

The two that matter most mirror W3's proof requirements directly:

  - test_head_loses_elements_is_regression: the planted-regression shape
    (head serialises fewer elements) must classify as `regression`, not
    `change`, even when the conductor key-set churns as a side effect.
  - test_head_gains_elements_is_improvement: the reverse direction.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from simulator import canon
from tools.abdiff.compare import (
    VERDICT_A_ONLY_FAILS,
    VERDICT_B_ONLY_FAILS,
    VERDICT_DIFFERS,
    VERDICT_SAME,
    Comparison,
)
from tools.refdiff import classify, normalize


def _diagram(order: str, element_uuids: list[str], conductor_keys: list[str]) -> dict:
    return {
        "order": order,
        "elements": {u: {"type": "x", "x": 0, "y": 0} for u in element_uuids},
        "conductors": {k: [{"terminals": [[k, k]], "type": "simple"}] for k in conductor_keys},
        "dynamic_texts": {},
        "raw_attrs": {},
    }


def _canon(element_uuids: list[str], conductor_keys: list[str] = ()) -> canon.Canon:
    uuids = {u: "element" for u in element_uuids}
    diagrams = [_diagram("0", element_uuids, list(conductor_keys))]
    return canon.Canon(
        diagrams=diagrams,
        uuid_universe=uuids,
        counts={
            "diagrams": 1,
            "elements": len(element_uuids),
            "conductors": len(conductor_keys),
            "terminals": 0,
            "uuids": len(uuids),
        },
    )


def _comparison(verdict: str, reasons=None) -> Comparison:
    return Comparison(verdict=verdict, reasons=reasons or [], a_failed=False, b_failed=False)


class TestClassify(unittest.TestCase):
    def test_head_loses_elements_is_regression(self):
        # Planted-regression shape: base has 3 elements, head serialised only 1.
        delta = classify.content_delta(
            _canon(["a", "b", "c"]),
            _canon(["a"]),
        )
        category, reasons = classify.classify(_comparison(VERDICT_DIFFERS), delta)
        self.assertEqual(category, classify.CATEGORY_REGRESSION)
        self.assertEqual(delta.lost_elements, ["b", "c"])
        self.assertTrue(any("lost 2 element" in r for r in reasons), reasons)

    def test_head_gains_elements_is_improvement(self):
        delta = classify.content_delta(
            _canon(["a"]),
            _canon(["a", "b", "c"]),
        )
        category, _ = classify.classify(_comparison(VERDICT_DIFFERS), delta)
        self.assertEqual(category, classify.CATEGORY_IMPROVEMENT)

    def test_value_only_change_is_change(self):
        # Same key-set, different value (an element moved) -- no loss/gain.
        delta = classify.content_delta(_canon(["a"]), _canon(["a"]))
        self.assertTrue(delta.empty)
        category, reasons = classify.classify(
            _comparison(VERDICT_DIFFERS, ["diagram order=0 elements value differs for ['a']"]),
            delta,
        )
        self.assertEqual(category, classify.CATEGORY_CHANGE)
        self.assertEqual(reasons, ["diagram order=0 elements value differs for ['a']"])

    def test_head_loses_conductor_is_regression(self):
        delta = classify.content_delta(
            _canon(["a", "b"], conductor_keys=["k1", "k2"]),
            _canon(["a", "b"], conductor_keys=["k1"]),
        )
        category, _ = classify.classify(_comparison(VERDICT_DIFFERS), delta)
        self.assertEqual(category, classify.CATEGORY_REGRESSION)
        self.assertEqual(delta.lost_conductors, ["k2"])

    def test_one_sided_failure_direction(self):
        self.assertEqual(
            classify.classify(_comparison(VERDICT_B_ONLY_FAILS))[0],
            classify.CATEGORY_REGRESSION,
        )
        self.assertEqual(
            classify.classify(_comparison(VERDICT_A_ONLY_FAILS))[0],
            classify.CATEGORY_IMPROVEMENT,
        )

    def test_same_is_same(self):
        self.assertEqual(classify.classify(_comparison(VERDICT_SAME))[0], classify.CATEGORY_SAME)

    def test_text_export_diff_without_delta_is_change(self):
        category, _ = classify.classify(_comparison(VERDICT_DIFFERS, ["out.csv differs"]), None)
        self.assertEqual(category, classify.CATEGORY_CHANGE)


class TestNormalize(unittest.TestCase):
    def _run(self, verb: str, text: str) -> str:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "out"
            p.write_text(text, encoding="utf-8")
            normalize.normalize_export(verb, p)
            return p.read_text(encoding="utf-8")

    def test_links_row_order_is_normalized(self):
        a = self._run("--export-links", "element;link_type;linked_to;folio;status\nA;x;;1;linked\nB;y;;2;linked\n")
        b = self._run("--export-links", "element;link_type;linked_to;folio;status\nB;y;;2;linked\nA;x;;1;linked\n")
        self.assertEqual(a, b)

    def test_bom_row_order_is_normalized(self):
        a = self._run("--export-bom", "label;qty\nA;1\nB;2\n")
        b = self._run("--export-bom", "label;qty\nB;2\nA;1\n")
        self.assertEqual(a, b)

    def test_nets_numbering_and_order_are_normalized(self):
        a = self._run("--export-nets", json_text(1, 2))
        b = self._run("--export-nets", json_text(2, 1))
        self.assertEqual(a, b)


def json_text(net_a: int, net_b: int) -> str:
    import json
    return json.dumps({
        "project": "p",
        "nets": 2,
        "list": [
            {"net": net_a, "wire_no": "W1", "terminals": [
                {"element": "E1", "terminal": "t1", "folio": 1},
                {"element": "E2", "terminal": "t1", "folio": 1},
            ]},
            {"net": net_b, "wire_no": "", "terminals": [
                {"element": "E3", "terminal": "t1", "folio": 2},
            ]},
        ],
    })


if __name__ == "__main__":
    unittest.main()
