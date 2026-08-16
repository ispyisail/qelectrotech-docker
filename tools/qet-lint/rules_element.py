"""E0xx rules over .elmt element files.

E001 -- file does not parse as XML (Python ElementTree).
E002 -- illegal XML 1.0 control character (same scan as P002).

The two rules are deliberately adjacent in the report: an element whose only
defect is a control character fires *both* -- it is not well-formed (E001) and
it contains an illegal control character (E002). That is correct, not a
double-count: E001 is "Python rejects it", E002 is "here is the byte that made
it illegal". They separate "the file is bad" (element collection) from "Qt
mishandles bad input" (the .qet loader) -- different bugs in different repos.
"""
from __future__ import annotations

import re

from model import Document, control_char_offsets
from report import Violation

# ElementTree's ParseError carries the position in prose: "line 4, column 35".
_POS_RE = re.compile(r"line (\d+)")


def e001_not_parseable(doc: Document):
    """The file is not well-formed XML, so QET (and ElementTree) cannot load it."""
    if doc.parse_error is None:
        return
    line = 0
    m = _POS_RE.search(doc.parse_error)
    if m:
        line = int(m.group(1))
    yield Violation(
        "E001", "error", doc.display_path, line,
        f"file does not parse as XML: {doc.parse_error}",
        evidence=doc.parse_error,
    )


def e002_control_char(doc: Document):
    """Illegal XML 1.0 control character in the element file (same scan as P002)."""
    for cc in control_char_offsets(doc.raw):
        line = doc.line_of_offset(cc.offset)
        if cc.form == "raw":
            desc = f"raw byte 0x{cc.code_point:02X}"
        else:
            desc = f"character reference &#{cc.code_point};"
        yield Violation(
            "E002", "error", doc.display_path, line,
            f"illegal XML 1.0 control character U+{cc.code_point:04X} ({desc})",
            evidence=f"byte offset {cc.offset}",
        )
