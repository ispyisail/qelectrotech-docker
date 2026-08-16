"""
Canonicalise a produced text export in place so two runs that differ only
in *serialization order* byte-compare equal.

Why this is needed (trap 2 in the brief): `Diagram::toXml` serialises
elements in `QGraphicsScene::items()` stacking order, which is not stable
across processes (FINDINGS.md F003/F004). Two of the five verbs leak that
same ordering into their *text* output, not just into `.qet` files:

  - `--export-links` iterates `Diagram::elements()` (which walks `items()`)
    to build its CSV, so its row order churns between processes -- verified:
    two runs of the same binary on `perceuse.qet` produced byte-different
    CSVs whose only difference was row order.
  - `--export-nets` assigns each net a `"net": N` number in
    `Diagram::conductors()` (`items()`) traversal order, so both the net
    numbering and the array order can churn between processes.

`--export-bom` is `ORDER BY label` (deterministic), but ties are broken by
the database's internal order, so it gets the same row-sort treatment for
safety. `--info` is already a deterministic JSON of counts; it is still
round-tripped through `json` with sorted keys so key order cannot matter.

None of these exports embed timestamps or absolute paths (the trap-4
normalisation targets those in *stdout/stderr*, which `tools/abdiff/compare.py`
already strips). What actually had to be normalised here is *order*, not
timestamps -- the brief's trap 2, manifesting in text form.

`.qet` / `.elmt` files are deliberately untouched: they are compared via
`simulator/canon.diff()` by `tools/abdiff/compare.py`, never byte-for-byte.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path


class NormalizeError(RuntimeError):
    """A text export could not be parsed into its canonical form."""


def _sort_csv_rows(text: str) -> str:
    """Return the CSV with data rows sorted (header row stays first).

    Parsed with the stdlib `csv` module rather than naive line-sorting so a
    quoted field containing an embedded newline or `;` (possible in QET's
    csvField, unlikely in these exports) does not split a row in two.
    """
    reader = csv.reader(io.StringIO(text), delimiter=";", quotechar='"')
    rows = [tuple(r) for r in reader]
    if not rows:
        return text
    header, data = rows[0], sorted(rows[1:])
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", quotechar='"',
                        quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(data)
    return buf.getvalue()


def _canon_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _normalize_nets(text: str) -> str:
    """Canonicalise --export-nets JSON: drop the traversal-assigned `net`
    number and array order, keeping the content-derived parts of each net
    (its wire_no and the *set* of terminals it connects)."""
    doc = json.loads(text)
    nets = []
    for net in doc.get("list", []):
        terminals = sorted(
            (t.get("element"), t.get("terminal"), t.get("folio"))
            for t in net.get("terminals", [])
        )
        nets.append({"wire_no": net.get("wire_no"), "terminals": terminals})
    nets.sort(key=lambda n: json.dumps(n, sort_keys=True))
    return _canon_json({
        "project": doc.get("project"),
        "nets": len(nets),
        "list": nets,
    })


def normalize_export(verb: str, path: Path) -> None:
    """Rewrite `path` (a produced text export for `verb`) into canonical form."""
    text = path.read_text(encoding="utf-8")
    if verb == "--export-nets":
        out = _normalize_nets(text)
    elif verb in ("--export-bom", "--export-links"):
        out = _sort_csv_rows(text)
    elif verb == "--info":
        out = _canon_json(json.loads(text))
    else:
        raise NormalizeError(f"no text normaliser for verb {verb!r}")
    path.write_text(out, encoding="utf-8")
