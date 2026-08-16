"""P0xx rules over .qet project files.

Each rule is a generator over a ``model.Document`` yielding ``Violation``s.

P001 -- NaN/Inf coordinate attribute. Delegated to
        ``simulator.canon.nan_or_inf_violations()`` (brief: "do not
        reimplement"); this module only attaches a source line.
P002 -- illegal XML 1.0 control character (raw byte or numeric character
        reference) anywhere in the file.
P003 -- duplicate uuid value within one project. Reuses the same uuid
        extraction canonicalize() uses to build ``uuid_universe`` (a
        ``root.iter()`` scan of ``uuid`` attributes), but flags only
        duplicates among ``<element>`` uuids -- the one value QET treats as a
        strict object identity. See the note in p003 below for why the full
        uuid universe cannot be used as-is.
"""
from __future__ import annotations

import collections

from simulator.canon import CanonError, nan_or_inf_violations

from model import Document, control_char_offsets
from report import Violation


def p001_nan_or_inf(doc: Document):
    """Flag any NaN/Inf coordinate. Detection is canon.py's, not ours."""
    try:
        found = nan_or_inf_violations(doc.path)
    except CanonError:
        # Not well-formed XML. That is not this rule's finding -- the
        # control-character scan (P002) owns byte-level corruption, and a
        # structurally broken project is simply unparseable.
        return
    for gv in found:
        line = doc.line_of_attr(gv.uuid, gv.field, gv.raw_value)
        yield Violation(
            "P001", "error", doc.display_path, line,
            f"{gv.tag} has {gv.field}=\"{gv.raw_value}\" ({gv.kind})",
            evidence=f'uuid={gv.uuid} {gv.field}="{gv.raw_value}"',
        )


def _describe(cc) -> str:
    if cc.form == "raw":
        return f"raw byte 0x{cc.code_point:02X}"
    return f"character reference &#{cc.code_point};"


def p002_control_char(doc: Document):
    """Illegal XML 1.0 control character anywhere in the project file."""
    for cc in control_char_offsets(doc.raw):
        line = doc.line_of_offset(cc.offset)
        yield Violation(
            "P002", "error", doc.display_path, line,
            f"illegal XML 1.0 control character U+{cc.code_point:04X} "
            f"({_describe(cc)})",
            evidence=f"byte offset {cc.offset}",
        )


def p003_duplicate_element_uuid(doc: Document):
    """Duplicate ``<element>`` uuid -- two objects sharing one identity.

    canonicalize() builds ``uuid_universe`` from *every* ``uuid`` attribute in
    the document and stores it in a dict, which silently dedups -- it cannot
    report duplicates. Counting occurrences over the full universe and flagging
    any repeat would fire ~500 times across the 23 known-good example projects:
    QET copies a sub-item's uuid when it instantiates an element or duplicates
    a folio, so ``terminal`` / ``dynamic_text`` / ``dynamic_elmt_text`` /
    ``link_uuid`` uuids repeat pervasively in files QET loads and renders
    correctly (hand-verified -- see README). That is a false-positive flood,
    not a finding.

    The one uuid that *is* a strict identity is the ``<element>`` uuid: it is
    what QET resolves conductors (via terminal uuid), cross-folio links
    (``link_uuid``) and undo/redo by, and it is empirically unique across all
    23 example projects. A duplicate here is real corruption.
    """
    if doc.tree is None:
        return
    counts: collections.Counter = collections.Counter(
        el.get("uuid") for el in doc.tree.iter("element") if el.get("uuid")
    )
    for uuid, n in sorted(counts.items()):
        if n <= 1:
            continue
        lines = doc.lines_of_uuid(uuid)
        line = lines[1] if len(lines) >= 2 else (lines[0] if lines else 0)
        yield Violation(
            "P003", "error", doc.display_path, line,
            f"uuid {uuid} appears on {n} <element> elements",
            evidence="duplicate element uuid (second occurrence)",
        )
