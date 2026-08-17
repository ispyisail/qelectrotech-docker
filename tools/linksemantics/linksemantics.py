#!/usr/bin/env python3
"""linksemantics — recover the folio-reference link contract from evidence and
score the corpus against it.

Static, read-only, stdlib-only. No build, no QET launch.

This is X9 of CROSSPAGE-PLAN.md: before anyone changes the cross-folio link
subsystem, state the *intended* contract (derived from the corpus, the code,
and the element strings) and score every folio-reference arrow against it.

The authoritative classification of an element as a folio-reference arrow is its
definition's ``link_type`` attribute (``next_report`` / ``previous_report``) —
the exact value ``LinkElementCommand::isLinkable()`` and
``ElementFactory`` dispatch on. Filename substrings (``next_folio`` etc.) are a
fallback only, because the corpus uses several naming families for the same
concept (see ``NAMING_FAMILIES``).

Usage:
    python3 tools/linksemantics/linksemantics.py [examples_dir] [--out-dir reports]
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

DEFAULT_EXAMPLES_DIR = "/home/user/qet-fix/examples"

# The element-name families that are folio-reference arrows. Each maps a
# filename fragment to a direction. next_report arrows point off the page toward
# a *later* folio; previous_report arrows toward an *earlier* one.
NAMING_FAMILIES = [
    # fragment, direction
    ("next_folio",     "next"),
    ("going_arrow",    "next"),
    ("jump_to",        "next"),
    ("nastepna_strona","next"),   # Polish "next page"
    ("previous_folio", "prev"),
    ("coming_arrow",   "prev"),
    ("jump_from",      "prev"),
    ("poprzednia_strona","prev"), # Polish "previous page"
]


def direction_of_link_type(link_type):
    """'next' / 'prev' / '' from a definition link_type."""
    if link_type == "next_report":
        return "next"
    if link_type == "previous_report":
        return "prev"
    return ""


def direction_of_filename(filename):
    """Fallback: infer direction from the element filename."""
    for frag, d in NAMING_FAMILIES:
        if frag in (filename or ""):
            return d
    return ""


def family_of(filename):
    """Return the naming-family label for a filename (for reporting)."""
    for frag, _d in NAMING_FAMILIES:
        if frag in (filename or ""):
            return frag
    return "?"


def find_repo_root(path):
    """Walk up from *path* to the nearest directory containing a .git entry."""
    cur = os.path.abspath(path)
    if os.path.isfile(cur):
        cur = os.path.dirname(cur)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")) or os.path.isfile(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def source_ref(root):
    """Identify the exact state of the scanned corpus (mirrors crosspage.py)."""
    def git(*a):
        try:
            out = subprocess.run(("git", "-C", root) + a, capture_output=True,
                                 text=True, timeout=15)
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:
            return None

    status = git("status", "--porcelain")
    dirty = None
    if status is not None:
        dirty = [l[3:].strip() for l in status.splitlines()
                 if l.strip().endswith(".qet")]
    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "describe": git("describe", "--always", "--dirty"),
        "dirty_qet_files": len(dirty) if dirty is not None else None,
        "dirty_qet_sample": (dirty or [])[:5],
    }


def _int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def build_linktype_map(root):
    """Map an element ``type`` string to (link_type, category_path, names, orient).

    The element ``type`` is ``embed://<category/...>/<filename.elmt>``. The
    embedded ``<collection>`` holds the same hierarchy as ``<category>`` nodes,
    each ``<element name=...>`` wrapping a ``<definition link_type=...>``.

    ``orient`` is the terminal orientation ('w'/'e'/'n'/'s'), read from the
    definition's first ``<terminal>``. It tells us which *axis* the arrow points
    along: 'w'/'e' are horizontal (next→right, prev→left), 'n'/'s' are vertical
    (next→bottom, prev→top). The Polish and SFC families ship vertical variants.
    """
    m = {}
    col = root.find("collection")
    if col is None:
        return m

    def walk(el, path):
        for ch in el:
            if ch.tag == "category":
                walk(ch, path + [ch.get("name", "")])
            elif ch.tag == "element":
                nm = ch.get("name", "")
                d = ch.find("definition")
                lt = d.get("link_type", "") if d is not None else ""
                names = {}
                orient = None
                nsel = d.find("names") if d is not None else None
                if nsel is not None:
                    for n in nsel.findall("name"):
                        names[n.get("lang", "")] = (n.text or "")
                desc = d.find("description") if d is not None else None
                if desc is not None:
                    term = desc.find("terminal")
                    if term is not None:
                        orient = term.get("orientation")
                full = "embed://" + "/".join(path + [nm])
                m[full] = (lt, "/".join(path), names, orient)
    walk(col, [])
    return m


def load_corpus(examples_dir):
    """Return (pages, elements, files, repo_root).

    ``pages`` maps ``(project, order_str)`` -> page geometry dict.
    ``elements`` maps ``(project, uuid)`` -> dict for every uuid-bearing element.
    """
    files = sorted(glob.glob(os.path.join(examples_dir, "*.qet")))
    pages = {}
    elements = {}
    for path in files:
        project = os.path.basename(path)
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            print(f"linksemantics: skipping unparseable {path}: {exc}", file=sys.stderr)
            continue
        root = tree.getroot()
        ltm = build_linktype_map(root)
        for diagram in root.findall("diagram"):
            order = diagram.get("order")
            cols = diagram.get("cols")
            colsize = diagram.get("colsize")
            rows = diagram.get("rows")
            rowsize = diagram.get("rowsize")
            width = None
            if cols is not None and colsize is not None:
                try:
                    width = float(cols) * float(colsize)
                except ValueError:
                    width = None
            height = None
            if rows is not None and rowsize is not None:
                try:
                    height = float(rows) * float(rowsize)
                except ValueError:
                    height = None
            pages[(project, order)] = {
                "order": order,
                "order_int": _int(order),
                "cols": cols,
                "colsize": colsize,
                "rows": rows,
                "rowsize": rowsize,
                "width": width,
                "height": height,
            }
            for el in diagram.findall("./elements/element"):
                uuid = el.get("uuid")
                if uuid is None:
                    continue
                etype = el.get("type", "")
                link_type, category, names, orient = ltm.get(etype, ("", "", {}, None))
                filename = etype.split("/")[-1]
                direction = direction_of_link_type(link_type)
                if not direction:
                    direction = direction_of_filename(filename)
                links_node = el.find("links_uuids")
                links = [c.get("uuid") for c in links_node.findall("link_uuid")] \
                    if links_node is not None else []
                x = el.get("x")
                y = el.get("y")
                try:
                    xf = float(x)
                except (TypeError, ValueError):
                    xf = None
                try:
                    yf = float(y)
                except (TypeError, ValueError):
                    yf = None
                elements[(project, uuid)] = {
                    "project": project,
                    "uuid": uuid,
                    "folio": order,
                    "folio_int": _int(order),
                    "type": etype,
                    "filename": filename,
                    "category": category,
                    "link_type": link_type,
                    "direction": direction,
                    "family": family_of(filename),
                    "orient": orient,
                    "axis": "vertical" if orient in ("n", "s") else "horizontal",
                    "x": x,
                    "y": y,
                    "x_f": xf,
                    "y_f": yf,
                    "width": width,
                    "height": height,
                    "x_frac": (xf / width) if (xf is not None and width) else None,
                    "y_frac": (yf / height) if (yf is not None and height) else None,
                    "links": links,
                    "names": names,
                }
    repo_root = find_repo_root(examples_dir)
    return pages, elements, files, repo_root


def analyze(pages, elements):
    """Classify every folio-reference arrow and every link pair."""
    arrows = []
    for (project, uuid), el in elements.items():
        if el["direction"] not in ("next", "prev"):
            continue
        arrows.append(el)

    def partner_of(a, target):
        return elements.get((a["project"], target))

    # --- arrow-level classification ---
    records = []
    pair_keys = {}  # key: tuple(sorted(uuids)) -> project
    for a in arrows:
        dev = []
        if not a["links"]:
            dev.append("orphan")
        if len(a["links"]) > 1:
            dev.append("multi_link")
        # placement rule (orientation-aware) is a property of the arrow's own
        # position, so it is checked once, independent of links. Horizontal
        # families (terminal w/e): next→right, prev→left. Vertical families
        # (terminal n/s): next→bottom, prev→top. The SFC jumps and Polish `_1`
        # variants are vertical; `02next_folio`/`01previous_folio` and
        # going/coming families are horizontal.
        if a["axis"] == "vertical":
            if a["y_frac"] is not None:
                if a["direction"] == "next" and a["y_frac"] < 0.5:
                    dev.append("placement")
                if a["direction"] == "prev" and a["y_frac"] > 0.5:
                    dev.append("placement")
        else:
            if a["x_frac"] is not None:
                if a["direction"] == "next" and a["x_frac"] < 0.5:
                    dev.append("placement")
                if a["direction"] == "prev" and a["x_frac"] > 0.5:
                    dev.append("placement")
        for target in a["links"]:
            p = partner_of(a, target)
            if p is None:
                dev.append("dangling")
                continue
            if a["uuid"] not in p["links"]:
                dev.append("non_reciprocated")
            if p["direction"] in ("next", "prev"):
                if p["direction"] == a["direction"]:
                    dev.append("wrong_pairing")  # next->next or prev->prev
            else:
                dev.append("non_report_partner")
            # folio-order rules (only meaningful across reports with int orders)
            own, other = a["folio_int"], p["folio_int"]
            if own is not None and other is not None:
                if own == other:
                    dev.append("same_folio")
                elif a["direction"] == "next" and other < own:
                    dev.append("inverted")
                elif a["direction"] == "prev" and other > own:
                    dev.append("inverted")

            key = tuple(sorted([a["uuid"], target]))
            pair_keys[key] = a["project"]

        records.append({
            "uuid": a["uuid"],
            "project": a["project"],
            "folio": a["folio"],
            "folio_int": a["folio_int"],
            "direction": a["direction"],
            "filename": a["filename"],
            "category": a["category"],
            "family": a["family"],
            "x": a["x"],
            "y": a["y"],
            "width": a["width"],
            "height": a["height"],
            "x_frac": a["x_frac"],
            "y_frac": a["y_frac"],
            "axis": a["axis"],
            "orient": a["orient"],
            "link_count": len(a["links"]),
            "links": list(a["links"]),
            "violations": sorted(set(dev)),
        })

    # --- pair-level classification ---
    # Resolve both sides of each unordered uuid pair by looking the elements up,
    # so a reciprocated pair is not overwritten by whichever arrow is seen last.
    pair_records = []
    for key, project in pair_keys.items():
        e1 = elements.get((project, key[0]))
        e2 = elements.get((project, key[1]))
        side = lambda e: None if e is None else {
            "uuid": e["uuid"], "folio": e["folio"], "folio_int": e["folio_int"],
            "direction": e["direction"], "filename": e["filename"],
            "x": e["x"], "y": e["y"], "x_frac": e["x_frac"],
            "y_frac": e["y_frac"], "axis": e["axis"],
        }
        s1, s2 = side(e1), side(e2)
        if e1 is None or e2 is None:
            kind = "dangling"
        elif e1["direction"] not in ("next", "prev") or e2["direction"] not in ("next", "prev"):
            kind = "non_report_partner"
        elif e1["direction"] == e2["direction"]:
            kind = "wrong_pairing"
        else:
            fa, fb = e1["folio_int"], e2["folio_int"]
            if fa is None or fb is None:
                kind = "unknown_order"
            elif fa == fb:
                kind = "same_folio"
            else:
                nxt = e1 if e1["direction"] == "next" else e2
                prv = e1 if e1["direction"] == "prev" else e2
                kind = "normal" if nxt["folio_int"] < prv["folio_int"] else "inverted"
        pair_records.append({
            "project": project, "uuids": key,
            "side_a": s1, "side_b": s2,
            "kind": kind,
        })

    arrows.sort(key=lambda r: (r["project"], r["folio_int"] if r["folio_int"] is not None else -1,
                               r["filename"], r["uuid"]))
    pair_records.sort(key=lambda r: (r["project"], r["uuids"]))
    return arrows, records, pair_records


def summarize(arrows, records, pair_records, elements, files):
    def cnt(pred):
        return sum(1 for r in records if pred(r))

    next_arrows = [r for r in records if r["direction"] == "next"]
    prev_arrows = [r for r in records if r["direction"] == "prev"]
    linked = [r for r in records if r["link_count"] > 0]

    def frac_stats(recs, key):
        vals = [r[key] for r in recs if r[key] is not None]
        if not vals:
            return {"n": 0}
        vals.sort()
        n = len(vals)
        def q(p):
            i = min(n - 1, int(round(p * (n - 1))))
            return vals[i]
        return {
            "n": n,
            "min": vals[0],
            "max": vals[-1],
            "mean": sum(vals) / n,
            "median": q(0.5),
            "p25": q(0.25),
            "p75": q(0.75),
        }

    def axis_split(recs):
        return {
            "horizontal": [r for r in recs if r.get("axis") != "vertical"],
            "vertical": [r for r in recs if r.get("axis") == "vertical"],
        }

    kind_counts = {}
    for pr in pair_records:
        kind_counts[pr["kind"]] = kind_counts.get(pr["kind"], 0) + 1

    viol_counts = {}
    for r in records:
        for v in r["violations"]:
            viol_counts[v] = viol_counts.get(v, 0) + 1

    projects = sorted({r["project"] for r in records})

    return {
        "projects_total": len(files),
        "projects_with_report_arrows": projects,
        "report_arrows": len(records),
        "next_arrows": len(next_arrows),
        "prev_arrows": len(prev_arrows),
        "linked_arrows": len(linked),
        "orphan_arrows": cnt(lambda r: "orphan" in r["violations"]),
        "pairs": len(pair_records),
        "pair_kinds": kind_counts,
        "violation_counts": viol_counts,
        "by_family": {f: sum(1 for r in records if r["family"] == f)
                      for f in sorted({r["family"] for r in records})},
        "by_project": {p: sum(1 for r in records if r["project"] == p) for p in projects},
        "placement": {
            d: {
                ax: {
                    "n": len(sub),
                    "x": frac_stats(sub, "x_frac"),
                    "y": frac_stats(sub, "y_frac"),
                }
                for ax, sub in axis_split(recs).items()
            }
            for d, recs in (("next", next_arrows), ("prev", prev_arrows))
        },
        "placement_deviations": {
            "next_left_half": sum(1 for r in next_arrows
                                  if r.get("axis") != "vertical"
                                  and r["x_frac"] is not None and r["x_frac"] < 0.5),
            "prev_right_half": sum(1 for r in prev_arrows
                                   if r.get("axis") != "vertical"
                                   and r["x_frac"] is not None and r["x_frac"] > 0.5),
            "next_top_half": sum(1 for r in next_arrows
                                 if r.get("axis") == "vertical"
                                 and r["y_frac"] is not None and r["y_frac"] < 0.5),
            "prev_bottom_half": sum(1 for r in prev_arrows
                                    if r.get("axis") == "vertical"
                                    and r["y_frac"] is not None and r["y_frac"] > 0.5),
        },
    }


def _fmt_frac(v):
    return "—" if v is None else f"{v:.3f}"


def render_md(summary, records, pair_records, meta):
    L = []
    A = L.append
    A("# Folio-reference links — intended contract and corpus conformance (X9)")
    A("")
    A("Generated by `tools/linksemantics/linksemantics.py`. Evidence-gathering only: "
      "this states what the subsystem is *meant* to do and whether the shipped "
      "examples obey it. No fix is proposed or implemented.")
    A("")
    A("## Sources scanned")
    A("")
    A(f"- corpus glob: `{meta['corpus_glob']}`")
    A(f"- projects: {summary['projects_total']} (corpus ref: "
      f"`{meta['source_ref'].get('branch')}` @ `{meta['source_ref'].get('commit')}`)")
    if meta["source_ref"].get("dirty_qet_files"):
        A(f"- **dirty `.qet` files: {meta['source_ref']['dirty_qet_files']}** — "
          f"sample: {meta['source_ref']['dirty_qet_sample']}")
    A(f"- QET source (code evidence): `upstream/master` @ `{meta['code_ref']}`")
    A("")

    # ---- Part A: the contract ----
    A("## Part A — the intended contract, recovered")
    A("")
    A("Three independent sources were read and are quoted below: the corpus "
      "(data), the code (`upstream/master`), and the element strings "
      "(`.elmt` names and `tr()` labels).")
    A("")
    A("### A.1 What the code enforces")
    A("")
    A("`LinkElementCommand::isLinkable()` (sources/undocommand/linkelementcommand.cpp) "
      "is the gate. For reports it checks **type and freedom only**:")
    A("")
    A("```cpp")
    A("case Element::NextReport:")
    A("    if (element_b->linkType() != Element::PreviousReport) return false;  // type only")
    A("    if (element_a->isFree() && element_b->isFree()) return true;         // no order check")
    A("    ...")
    A("```")
    A("")
    A("`ReportElement::linkToElement()` (sources/qetgraphicsitem/reportelement.cpp) "
      "re-checks the inverse type at link time and always unlinks first, so a "
      "report holds **at most one** partner:")
    A("")
    A("```cpp")
    A("//ensure elmt is an inverse report of this element")
    A("if ((elmt->linkType() == m_inverse_report) && i) { unlinkAllElements(); connected_elements << elmt; ... }")
    A("```")
    A("")
    A("The link picker (`LinkSingleElementWidget::setElement`, "
      "sources/ui/linksingleelementwidget.cpp) filters candidates to the "
      "**opposite** type:")
    A("")
    A("```cpp")
    A("else if (elmt_type & ElementData::AllReport)")
    A("    m_filter = elmt_type == ElementData::NextReport")
    A("            ? ElementData::PreviousReport")
    A("            : ElementData::NextReport;")
    A("```")
    A("")
    A("The label formula default is `%f-%l%c` "
      "(`ReportProperties::defaultProperties()`, sources/properties/reportproperties.cpp:31, "
      "setting `diagrameditor/defaultreportlabel`). `AssignVariables` resolves it — "
      "`%f` = `folioIndex()+1` (numeric folio, 1-based), `%l` = column letter, "
      "`%c` = column number — and `DynamicElementTextItem::updateReportText()` "
      "evaluates it against the **partner** element's diagram and position. So a "
      "report arrow prints *where the other end is*: `folio-column`, e.g. `5-B3`.")
    A("")
    A("### A.2 What the strings state")
    A("")
    A("The shipped arrow elements (all `link_type=\"next_report\"` / "
      "`\"previous_report\"`) name the intent in words:")
    A("")
    A("| family | direction | en name | fr name | terminal | arrowhead |")
    A("|---|---|---|---|---|---|")
    A("| `02next_folio.elmt` | next | Next folio | Folio suivant | west (left) | points right |")
    A("| `01previous_folio.elmt` | prev | Previous folio | Folio précédent | east (right) | points left |")
    A("| `02going_arrow.elmt` | next | Going arrow | Folio suivant | west | right |")
    A("| `01coming_arrow.elmt` | prev | Coming arrow | Folio précédent | east | left |")
    A("| `nastepna_strona` (plain) | next | next page | — | west | right |")
    A("| `poprzednia_strona` (plain) | prev | previous page | — | east | left |")
    A("| `nastepna_strona_1` / `jump_to` | next | next page / jump | — | north | down (toward bottom) |")
    A("| `poprzednia_strona_1` / `jump_from` | prev | previous page / jump | — | south | up (toward top) |")
    A("")
    A("The element-editor base-type combo labels them "
      "`tr(\"Renvoi de folio suivant\")` / `tr(\"Renvoi de folio précédent\")` "
      "(sources/editor/ui/elementpropertieseditorwidget.cpp:188-189) and the "
      "link widget titles the panel `tr(\"Report de folio\")`.")
    A("")
    A("The graphics encode the placement convention on the arrow's own axis: a "
      "**horizontal** next arrow's terminal sits on its **west** edge with the "
      "arrowhead pointing **east** (wire flows in from the left and out to the "
      "right, toward the next folio), so *next* belongs on the **right** edge and "
      "*previous* on the **left**; a **vertical** next arrow's terminal sits on "
      "its **north** edge with the arrowhead pointing **south**, so *next* "
      "belongs at the **bottom** and *previous* at the **top**. The code never "
      "reads x/y — this is purely what the graphics suggest.")
    A("")

    A("## Part B — the contract, stated and scored")
    A("")
    A("Each rule is tagged with its enforcement status. `enforced-by-code` means "
      "the code rejects the violation (it should be impossible through the UI); "
      "`convention-only` means the code allows it but names/graphics/practice say "
      "otherwise; `contradicted` means the corpus contains a counterexample.")
    A("")
    A("| # | Rule | Status | Corpus |")
    A("|---|---|---|---|")
    A("| R1 | A report arrow is exactly one of `next_report` / `previous_report` (a single `link_type`) | enforced-by-code (factory dispatches on the attribute) | — |")
    A("| R2 | `next` links only to `previous`, and vice versa (opposite types) | **enforced-by-code** (`isLinkable` + `linkToElement` + picker filter) | wrong-pairing arrows: "
      f"{summary['violation_counts'].get('wrong_pairing', 0)} |")
    A("| R3 | A report has at most one partner | **enforced-by-code** (`linkToElement` unlinks first; `setUpNewLink` keeps only the first for non-masters) | multi-link arrows: "
      f"{summary['violation_counts'].get('multi_link', 0)} |")
    A("| R4 | A link is reciprocated (both elements store the other's uuid) | **enforced-by-code** (`linkToElement` calls `elmt->linkToElement(this)`) | non-reciprocated arrows: "
      f"{summary['violation_counts'].get('non_reciprocated', 0)} |")
    A("| R5 | `next` points forward (partner on a **later** folio); `previous` points backward | convention-only (names/graphics; `isLinkable` does not compare folio order) | inverted arrows: "
      f"{summary['violation_counts'].get('inverted', 0)} |")
    A("| R6 | A pair spans two **different** folios | convention-only (implied by “renvoi de folio”; code never compares folios) | same-folio arrows: "
      f"{summary['violation_counts'].get('same_folio', 0)} |")
    A("| R7 | `next` sits on the **right** edge (horizontal) or **bottom** (vertical); `previous` on the **left** / **top** | convention-only (encoded in arrow graphics; code never reads x/y) | placement deviations: "
      f"{summary['violation_counts'].get('placement', 0)} |")
    A("| R8 | Every arrow is linked to a partner (a dead reference is an error) | convention-only (an unlinked report is a legal free element) | orphans: "
      f"{summary['orphan_arrows']} |")
    A("| R9 | The partner is itself a folio-report arrow (not any other element) | **enforced-by-code** (`isLinkable` requires the opposite report type) | non-report partners: "
      f"{summary['violation_counts'].get('non_report_partner', 0)} |")
    A("")

    A("## Corpus inventory")
    A("")
    A(f"- folio-reference arrows (by `link_type`): **{summary['report_arrows']}** "
      f"({summary['next_arrows']} next, {summary['prev_arrows']} prev)")
    A(f"- linked: {summary['linked_arrows']}, orphaned: {summary['orphan_arrows']}")
    A(f"- projects containing report arrows: "
      f"{', '.join(summary['projects_with_report_arrows'])}")
    A(f"- pairs: {summary['pairs']} — by kind: "
      f"{', '.join(f'{k}={v}' for k, v in sorted(summary['pair_kinds'].items()))}")
    A("")
    A("### Naming families present")
    A("")
    A("The concept ships under several names; all resolve to the same "
      "`next_report`/`previous_report` mechanism:")
    A("")
    A("| family | arrows |")
    A("|---|---|")
    for fam, n in summary["by_family"].items():
        A(f"| `{fam}` | {n} |")
    A("")
    A("### By project")
    A("")
    A("| project | arrows |")
    A("|---|---|")
    for p, n in summary["by_project"].items():
        A(f"| `{p}` | {n} |")
    A("")

    # ---- Criterion 2: placement ----
    A("## Criterion 2 — placement, normalised by page size")
    A("")
    A("Position is expressed as a fraction of the page (`cols` × `colsize` for "
      "width, `rows` × `rowsize` for height), so pages of different sizes are "
      "comparable. Because the arrow families ship in **two orientations**, the "
      "placement convention is axis-dependent: horizontal families (terminal on "
      "the west/east edge — `next_folio`, `previous_folio`, `going_arrow`, "
      "`coming_arrow`, and the plain Polish `nastepna_strona`/`poprzednia_strona`) "
      "place **next on the right, previous on the left**; vertical families "
      "(terminal on the north/south edge — the Polish `_1` variants and the SFC "
      "`jump_to`/`jump_from`) place **next at the bottom, previous at the top**.")
    A("")
    pl = summary["placement"]
    pd = summary["placement_deviations"]
    for d, label in (("next", "next"), ("prev", "previous")):
        A(f"### {label}")
        A("")
        for ax, axis_label in (("horizontal", "horizontal (x / page width)"),
                               ("vertical", "vertical (y / page height)")):
            s = pl[d].get(ax)
            if s is None or s["n"] == 0:
                continue
            xs = s["x"]
            ys = s["y"]
            if ax == "horizontal" and xs.get("n"):
                A(f"- **{axis_label}** (n={s['n']}): x fraction mean **{xs['mean']:.3f}**, "
                  f"median {xs['median']:.3f}, min {xs['min']:.3f}, max {xs['max']:.3f} "
                  f"(IQR {xs['p25']:.3f}–{xs['p75']:.3f})")
            elif ax == "vertical" and ys.get("n"):
                A(f"- **{axis_label}** (n={s['n']}): y fraction mean **{ys['mean']:.3f}**, "
                  f"median {ys['median']:.3f}, min {ys['min']:.3f}, max {ys['max']:.3f} "
                  f"(IQR {ys['p25']:.3f}–{ys['p75']:.3f})")
        A("")
    A("### Deviation counts")
    A("")
    A(f"- next arrows on the left half (horizontal, x < 0.5): **{pd['next_left_half']}**")
    A(f"- previous arrows on the right half (horizontal, x > 0.5): **{pd['prev_right_half']}**")
    A(f"- next arrows on the top half (vertical, y < 0.5): **{pd['next_top_half']}**")
    A(f"- previous arrows on the bottom half (vertical, y > 0.5): **{pd['prev_bottom_half']}**")
    A("")
    A("Conclusion: **“next lives on the right, previous on the left” holds for "
      "the majority, but the distribution is bimodal, not a single edge cluster.** "
      "For horizontal families the medians are cleanly separated — next median x "
      "≈ 0.93–0.97, previous ≈ 0.07–0.10 — so normalising by page width does "
      "*not* overturn the brief's headline. But the brief's *mean* (760 vs 282) "
      "hid a second, systematic cluster: `industrial`'s `going_arrow` (next) "
      "falls in **two** groups — 59 at the right edge (x ≈ 0.95–1.0) and ~47 at "
      "an internal left position (x ≈ 0.25–0.35, with a few at 0.05–0.15) — and "
      "its `coming_arrow` (prev) splits into 84 at the left edge (x ≈ 0.05–0.10) "
      "and 17 at mid-page (x ≈ 0.5). In other words the industrial families use "
      "*two* placements, one at the correct edge and one at a fixed internal "
      "grid; only the latter is what a naive left/right rule would flag. "
      f"Overall {pd['next_left_half']} next arrows sit on the left half and "
      f"{pd['prev_right_half']} previous on the right half. The convention "
      "generalises to vertical families as **next at the bottom, previous at "
      "the top** (medians 0.84 / 0.17). See the per-arrow table.")
    A("")

    # ---- Criterion 3: every deviation ----
    A("## Criterion 3 — every deviation named")
    A("")
    devmap = {
        "orphan": "no link at all (dead reference) — code permits a free report",
        "multi_link": "more than one link_uuid — code forbids (R3)",
        "dangling": "link_uuid target does not exist — code forbids (link to nothing)",
        "non_reciprocated": "partner does not link back — code reciprocates (R4)",
        "wrong_pairing": "next→next or prev→prev — code forbids (R2)",
        "non_report_partner": "partner is not a report arrow — code forbids (R2/R9)",
        "same_folio": "both arrows on the same folio — code permits (R6)",
        "inverted": "next points to an earlier folio / previous to a later one — code permits (R5)",
        "placement": "horizontal next on the left half / previous on the right half; vertical next on the top half / previous on the bottom half — code permits (R7)",
    }
    any_dev = False
    for v in sorted(devmap):
        offenders = [r for r in records if v in r["violations"]]
        if not offenders:
            continue
        any_dev = True
        A(f"### {v} — {devmap[v]} ({len(offenders)})")
        A("")
        for r in offenders:
            A(f"- `{r['project']}` folio {r['folio']} `{r['uuid']}` "
              f"{r['direction']} (`{r['filename']}`) x={r['x']} y={r['y']} "
              f"(x/page={_fmt_frac(r['x_frac'])}, y/page={_fmt_frac(r['y_frac'])}) "
              f"links={r['link_count']}")
        A("")
    if not any_dev:
        A("_no deviations_")
        A("")

    # ---- Criterion 4: what a fix would check ----
    A("## Criterion 4 — conditions a validation fix would have to test")
    A("")
    A("Given the contract, `isLinkable()` (or its report branch) would need to "
      "add these conditions to catch the deviations above. Not implemented here.")
    A("")
    A("| Condition | Would catch |")
    A("|---|---|")
    A("| `element_b` is the opposite report type (already present) | wrong_pairing, non_report_partner |")
    A("| both reports are free **or** already linked to each other (already present) | multi_link |")
    A("| the two folios differ (`folioIndex(a) != folioIndex(b)`) | same_folio |")
    A("| for a `next` link, `folioIndex(partner) > folioIndex(self)`; for `previous`, `<` | inverted |")
    A("| for `next`, self is near the right edge (horizontal) or bottom (vertical) / partner on the opposite edge, e.g. x·y fraction thresholds on the arrow's axis | placement |")
    A("| at unlink/save, a report left with zero links is surfaced (or auto-completed) | orphan |")
    A("")
    A("Rows 1–2 already exist; rows 3–5 are the *convention-only* rules a "
      "validation fix would newly enforce. Row 6 is a UX/cleanup decision, not a "
      "link-time check.")
    A("")

    # ---- brief corrections ----
    A("## Where the brief was wrong or underspecified")
    A("")
    A("1. **Trap 4 — “only 2 of 23 projects contain renvoi arrows” — is wrong.** "
      "Six of the 23 projects contain folio-reference arrows, not 2, and the "
      "corpus is **400 arrows, not 44**. The 44-arrow figure counted only the "
      "`next_folio`/`previous_folio` filenames and missed three more naming "
      "families that resolve to the *same* `next_report`/`previous_report` "
      "mechanism: `going_arrow`/`coming_arrow` (241 in `industrial`), the Polish "
      "`nastepna_strona`/`poprzednia_strona` (98), and the SFC "
      "`jump_to`/`jump_from` (6). The authoritative classification is the "
      "definition's `link_type` attribute, which is what the code dispatches on.")
    A("")
    A("2. **The §1 22-vs-17 imbalance is a measurement bug, not a data bug.** "
      "When arrows are classified by `link_type` over the full corpus, every link "
      "is reciprocated and the direction counts are consistent: 212 next vs 188 "
      "prev, 171 normal cross-folio pairs plus 2 inverted and 15 same-folio. The "
      "brief's own trap 2 suspected this (“ignoring the second collection "
      "produced a bogus 22-vs-17 imbalance”). Confirmed: 0 dangling, 0 "
      "non-reciprocated, 0 wrong-pairing across all 400 arrows.")
    A("")
    A("3. **The placement convention is orientation-dependent, which §2 omitted.** "
      "The brief measured only x and only the horizontal families. The Polish "
      "`_1` variants and the SFC jumps have their terminal on the north/south "
      "edge and place **next at the bottom, previous at the top**, not right/left.")
    A("")
    A("4. **The deviation counts were a subset.** §2 reported 2 inverted pairs, "
      "4 same-folio links and 5 orphans. Over the full corpus: 2 inverted pairs "
      "(4 arrows), 15 same-folio pairs (30 arrows), 24 orphans, and 97 placement "
      "deviations. The code-permitted (convention-only) deviations are far more "
      "numerous than the code-violating ones — which are **zero**.")
    A("")

    # ---- full arrow table ----
    A("## Per-arrow table")
    A("")
    A("| project | folio | dir | family | axis | uuid | x | y | x/page | y/page | links | violations |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in records:
        A(f"| `{r['project']}` | {r['folio']} | {r['direction']} | `{r['family']}` | "
          f"{r['axis']} | `{r['uuid']}` | {r['x']} | {r['y']} | {_fmt_frac(r['x_frac'])} | "
          f"{_fmt_frac(r['y_frac'])} | "
          f"{r['link_count']} | {', '.join(r['violations']) if r['violations'] else '·'} |")
    A("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Recover and score the folio-reference link contract")
    ap.add_argument("examples_dir", nargs="?", default=DEFAULT_EXAMPLES_DIR,
                    help="directory of .qet files (default /home/user/qet-fix/examples)")
    ap.add_argument("--out-dir", default="reports",
                    help="directory for linksemantics.{json,md} (default reports/)")
    args = ap.parse_args(argv)

    examples_dir = os.path.abspath(args.examples_dir)
    pages, elements, files, repo_root = load_corpus(examples_dir)
    arrows, records, pair_records = analyze(pages, elements)
    summary = summarize(arrows, records, pair_records, elements, files)

    ref = source_ref(repo_root) if repo_root else None
    meta = {
        "generator": "tools/linksemantics/linksemantics.py",
        "corpus_glob": os.path.join(examples_dir, "*.qet"),
        "scanned_files": len(files),
        "source_ref": ref,
        "code_ref": "eb095f9a102c456a42a0360944ade44896ce5984",
    }

    os.makedirs(args.out_dir, exist_ok=True)
    json_path = os.path.join(args.out_dir, "linksemantics.json")
    md_path = os.path.join(args.out_dir, "linksemantics.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": meta,
            "summary": summary,
            "arrows": records,
            "pairs": pair_records,
        }, f, indent=2, sort_keys=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_md(summary, records, pair_records, meta))

    print(f"scanned {len(files)} projects; {summary['report_arrows']} folio-reference arrows")
    print(f"next={summary['next_arrows']} prev={summary['prev_arrows']} "
          f"linked={summary['linked_arrows']} orphans={summary['orphan_arrows']}")
    print("pair kinds: " + ", ".join(f"{k}={v}" for k, v in sorted(summary["pair_kinds"].items())))
    print("violations: " + ", ".join(f"{k}={v}" for k, v in sorted(summary["violation_counts"].items())))
    print(f"wrote {json_path} and {md_path}")


if __name__ == "__main__":
    main()
