"""Hermetic tests for qet-lint's five rules + baseline diffing.

Run from the repo root:

    python3 -m unittest discover -s tools/qet-lint/tests -v

The fixtures are synthetic (written to a temp dir), so the tests do not
depend on the QET element collection or example projects existing anywhere.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]   # tools/qet-lint
_REPO = Path(__file__).resolve().parents[3]  # repo root
for _p in (_PKG, _REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import model                      # noqa: E402
import report                     # noqa: E402
import rules_element as re_el      # noqa: E402
import rules_project as re_proj    # noqa: E402


def _run(path: Path, rules):
    doc = model.load(path, display_path=str(path))
    return list(v for rule in rules for v in rule(doc))


class ControlCharTest(unittest.TestCase):
    def test_raw_nul_is_flagged(self):
        found = model.control_char_offsets(b"a\x00b")
        self.assertEqual([(f.form, f.code_point, f.offset) for f in found],
                         [("raw", 0x00, 1)])

    def test_charref_is_flagged(self):
        found = model.control_char_offsets(b"x &#11; y")
        self.assertEqual([(f.form, f.code_point) for f in found],
                         [("charref", 0x0B)])

    def test_hex_charref_is_flagged(self):
        found = model.control_char_offsets(b"x &#x0B; y")
        self.assertEqual([(f.form, f.code_point) for f in found],
                         [("charref", 0x0B)])

    def test_legal_controls_are_not_flagged(self):
        # tab, LF, CR are the only legal ASCII controls in XML 1.0.
        self.assertEqual(model.control_char_offsets(b"\t\n\r"), [])
        # a reference to a *legal* control is not a violation.
        self.assertEqual(model.control_char_offsets(b"&#10;&#13;&#9;"), [])


class ProjectRulesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _write(self, name: str, content: bytes) -> Path:
        p = self.dir / name
        p.write_bytes(content)
        return p

    def test_p001_flags_nan_coordinate(self):
        p = self._write("nan.qet", (
            b'<project><diagram order="0">'
            b'<element type="t" x="nan" y="10" uuid="{11111111-2222-3333-4444-555555555555}"/>'
            b'</diagram></project>'
        ))
        vs = _run(p, (re_proj.p001_nan_or_inf,))
        self.assertEqual(len(vs), 1)
        self.assertEqual(vs[0].rule_id, "P001")
        self.assertIn('x="nan"', vs[0].message)

    def test_p001_ignores_finite_coordinates(self):
        p = self._write("ok.qet", (
            b'<project><diagram order="0">'
            b'<element type="t" x="10.5" y="-3" uuid="{11111111-2222-3333-4444-555555555555}"/>'
            b'</diagram></project>'
        ))
        self.assertEqual(_run(p, (re_proj.p001_nan_or_inf,)), [])

    def test_p002_flags_raw_nul(self):
        p = self._write("nul.qet", b'<project>\x00</project>')
        vs = _run(p, (re_proj.p002_control_char,))
        self.assertEqual(len(vs), 1)
        self.assertEqual(vs[0].rule_id, "P002")
        self.assertEqual(vs[0].line, 1)

    def test_p002_flags_charref(self):
        p = self._write("ref.qet", b'<project>&#11;</project>')
        vs = _run(p, (re_proj.p002_control_char,))
        self.assertEqual(len(vs), 1)
        self.assertIn("U+000B", vs[0].message)

    def test_p003_flags_duplicate_element_uuid(self):
        p = self._write("dup.qet", (
            b'<project>'
            b'<diagram order="0">'
            b'<element type="a" x="1" y="1" uuid="{11111111-2222-3333-4444-555555555555}"/>'
            b'<element type="b" x="2" y="2" uuid="{11111111-2222-3333-4444-555555555555}"/>'
            b'</diagram></project>'
        ))
        vs = _run(p, (re_proj.p003_duplicate_element_uuid,))
        self.assertEqual(len(vs), 1)
        self.assertEqual(vs[0].rule_id, "P003")
        self.assertIn("appears on 2", vs[0].message)

    def test_p003_ignores_unique_uuids(self):
        p = self._write("uniq.qet", (
            b'<project><diagram order="0">'
            b'<element type="a" x="1" y="1" uuid="{11111111-2222-3333-4444-555555555555}"/>'
            b'<element type="b" x="2" y="2" uuid="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}"/>'
            b'</diagram></project>'
        ))
        self.assertEqual(_run(p, (re_proj.p003_duplicate_element_uuid,)), [])

    def test_p003_ignores_terminal_uuid_copies(self):
        # QET copies terminal uuids when instantiating an element; P003 is
        # scoped to <element> uuids and must not flag those copies.
        p = self._write("termdup.qet", (
            b'<project><diagram order="0">'
            b'<element type="a" x="1" y="1" uuid="{11111111-2222-3333-4444-555555555555}">'
            b'<terminal x="0" y="0" uuid="{tttttttt-tttt-tttt-tttt-tttttttttttt}"/>'
            b'</element>'
            b'<element type="b" x="2" y="2" uuid="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}">'
            b'<terminal x="0" y="0" uuid="{tttttttt-tttt-tttt-tttt-tttttttttttt}"/>'
            b'</element>'
            b'</diagram></project>'
        ))
        self.assertEqual(_run(p, (re_proj.p003_duplicate_element_uuid,)), [])


class ElementRulesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _write(self, name: str, content: bytes) -> Path:
        p = self.dir / name
        p.write_bytes(content)
        return p

    def test_e001_flags_unparseable(self):
        p = self._write("bad.elmt", b"<definition><name></definition>")
        vs = _run(p, (re_el.e001_not_parseable,))
        self.assertEqual(len(vs), 1)
        self.assertEqual(vs[0].rule_id, "E001")

    def test_e001_clean_file(self):
        p = self._write("ok.elmt", b'<definition version="0.100.0"/>')
        self.assertEqual(_run(p, (re_el.e001_not_parseable,)), [])

    def test_e002_flags_charref(self):
        # The xpx.elmt fixture: &#11; (U+000B) in a <name lang="ca"> element.
        p = self._write("xpx.elmt",
                        b'<definition version="0.100.0">\n<names>\n'
                        b'<name lang="ca">Unitat &#11;erge</name>\n</names>\n</definition>\n')
        vs = _run(p, (re_el.e002_control_char,))
        self.assertEqual(len(vs), 1)
        self.assertEqual(vs[0].rule_id, "E002")
        self.assertEqual(vs[0].line, 3)


class BaselineTest(unittest.TestCase):
    def test_compare_regression_and_improvement(self):
        base = {"a.qet": {"P002": 1}}
        cur = {"a.qet": {"P002": 2}, "b.qet": {"P001": 1}}
        regressions, improvements = report.compare_baseline(cur, base)
        self.assertEqual(regressions, [("a.qet", "P002", 2, 1), ("b.qet", "P001", 1, 0)])
        self.assertEqual(improvements, [])

    def test_compare_improvement(self):
        base = {"a.qet": {"P002": 2}}
        cur = {"a.qet": {"P002": 0}}
        regressions, improvements = report.compare_baseline(cur, base)
        self.assertEqual(regressions, [])
        self.assertEqual(improvements, [("a.qet", "P002", 0, 2)])

    def test_build_current_and_roundtrip(self):
        vs = [report.Violation("P002", "error", "a.qet", 1, "x"),
              report.Violation("P002", "error", "a.qet", 2, "y"),
              report.Violation("E001", "error", "b.elmt", 0, "z")]
        current = report.build_current(vs)
        self.assertEqual(current, {"a.qet": {"P002": 2}, "b.elmt": {"E001": 1}})


if __name__ == "__main__":
    unittest.main()
