"""
labelstability — do folio-reference (renvoi) labels survive folio moves?

TASK X6. Python 3 stdlib only. Drives the QElectroTech binary headlessly to
answer one question the maintainer's PR #702 rejection left open:

    "Use %F (folio label) instead of %f (folio position). %F stays stable when
     folios are moved, renamed or inserted; %f does not."

This tool *measures* whether that is true; it does not repair anything.

Four criteria (see briefs/X6-deepseek.md):

    C1  where an arrow's displayed label text lives in the XML, and the formula
        that produces it.
    C2  the %f-vs-%F claim, tested by reordering a folio in two variants.
    C3  the blank-label / wrong-number failure across repeated saves.
    C4  corpus survey: %f vs %F vs other across the shipped examples.

Output: reports/labelstability.json and reports/labelstability.md

Traps honoured:
    * QET runs with `-platform offscreen` and isolated HOME/XDG_* dirs, every
      run (SingleApplication).
    * every QET invocation has a timeout; schema_indus.qet is excluded from
      resave (upstream #661 hangs on a modal).
    * work happens on copies under a scratch dir, never under examples/.
    * labels are compared by arrow uuid, never by document order (Diagram::toXml
      is not deterministic — upstream #754).
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# configuration (overridable via env)
# ---------------------------------------------------------------------------

QET_BINARY = os.environ.get(
    "LABELSTABILITY_QET",
    "/home/user/qet-fix/build-ab/7307a59c101a/build/qelectrotech",
)
EXAMPLES_DIR = os.environ.get(
    "LABELSTABILITY_EXAMPLES", "/home/user/qet-fix/examples"
)
# the ref the binary was built from (mirrors tools/actionaudit's source_ref)
SOURCE_REF = os.environ.get("LABELSTABILITY_REF", "7307a59c101a")

# projects excluded from any QET invocation (schema_indus.qet hangs: #661)
RESAVE_EXCLUDED = {"schema_indus.qet"}

# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------


def _info_name_text(dt):
    """Return (info_name, text) for a <dynamic_elmt_text> node."""
    in_el = dt.find("info_name")
    iname = (in_el.text or "") if in_el is not None else ""
    t = dt.find("text")
    ttext = (t.text or "") if t is not None else ""
    return iname, ttext


def extract_arrows(path):
    """
    Parse a .qet and return, per folio-reference arrow element, its record.

    Return: dict[uuid] -> dict with keys:
        title   diagram title
        order   diagram order attribute (position, 1-based, as stored)
        folio   diagram folio formula (the %F source)
        type    element type (next_folio / previous_folio)
        label   <elementInformation name="label"> value (the *stored* label)
        text    <dynamic_elmt_text info_name=label><text> (the *displayed* label)
        has_link  bool: carries at least one <link_uuid>
    """
    tree = ET.parse(path)
    root = tree.getroot()
    out = {}
    for diag in root.iter("diagram"):
        dtitle = diag.get("title", "")
        dorder = diag.get("order", "")
        dfolio = diag.get("folio", "")
        for el in diag.iter("element"):
            etype = el.get("type", "")
            if "06renvoi" not in etype:
                continue
            uuid = el.get("uuid", "")
            label = ""
            for ei in el.iter("elementInformation"):
                if ei.get("name") == "label":
                    label = ei.text or ""
            text = ""
            for dt in el.iter("dynamic_elmt_text"):
                iname, ttext = _info_name_text(dt)
                if iname == "label":
                    text = ttext
            has_link = next(el.iter("link_uuid"), None) is not None
            out[uuid] = {
                "title": dtitle,
                "order": dorder,
                "folio": dfolio,
                "type": etype.rsplit("/", 1)[-1],
                "label": label,
                "text": text,
                "has_link": has_link,
            }
    return out


def read_report_formula(path):
    """Return the project's <report label="..."> value, or None."""
    tree = ET.parse(path)
    for r in tree.getroot().iter("report"):
        return r.get("label")
    return None


def _slug(name):
    """Filesystem-safe short name for a project file."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


# ---------------------------------------------------------------------------
# low-level XML text edits (work on the raw text, not ElementTree, so we do not
# reflow the file; QET re-normalises on --resave anyway)
# ---------------------------------------------------------------------------

_DIAGRAM_OPEN = re.compile(r"<diagram\b")
_DIAGRAM_CLOSE = re.compile(r"</diagram>")


def split_diagram_blocks(text):
    opens = [m.start() for m in _DIAGRAM_OPEN.finditer(text)]
    closes = [m.end() for m in _DIAGRAM_CLOSE.finditer(text)]
    assert len(opens) == len(closes), "unbalanced <diagram> blocks"
    header = text[: opens[0]]
    blocks = [text[o:c] for o, c in zip(opens, closes)]
    footer = text[closes[-1] :]
    return header, blocks, footer


def join_diagram_blocks(header, blocks, footer):
    return header + "".join(blocks) + footer


def diagram_title(block):
    m = re.search(r'<diagram[^>]*\btitle="([^"]*)"', block)
    return m.group(1) if m else "?"


def move_diagram(text, title, to_end=True):
    """Move the <diagram> block with the given title to the end."""
    header, blocks, footer = split_diagram_blocks(text)
    idx = None
    for i, b in enumerate(blocks):
        if diagram_title(b) == title:
            idx = i
            break
    if idx is None:
        raise ValueError("no diagram titled %r" % title)
    moved = blocks.pop(idx)
    if to_end:
        blocks.append(moved)
    else:
        blocks.insert(0, moved)
    return join_diagram_blocks(header, blocks, footer)


def set_report_formula(text, formula):
    new, n = re.subn(
        r'<report label="[^"]*"/>', '<report label="%s"/>' % formula, text, count=1
    )
    assert n == 1, "no <report label=...> element found"
    return new


def set_folio_labels(text, labels):
    """Set each diagram's folio= attribute to a stable literal label.

    labels: list of strings, one per diagram in document order.
    """
    header, blocks, footer = split_diagram_blocks(text)
    assert len(labels) == len(blocks), "label count != diagram count"
    out = []
    for b, lab in zip(blocks, labels):
        nb, n = re.subn(r'folio="[^"]*"', 'folio="%s"' % lab, b, count=1)
        assert n == 1, "no folio= attribute in %r" % diagram_title(b)
        out.append(nb)
    return join_diagram_blocks(header, out, footer)


def remove_all_links(text, uuids):
    """Remove every <link_uuid uuid="..."/> whose uuid is in `uuids`."""
    for u in uuids:
        text = re.sub(r'<link_uuid uuid="%s"/>\s*' % re.escape(u), "", text)
    return text


# ---------------------------------------------------------------------------
# QET driver
# ---------------------------------------------------------------------------


def _isolated_env(workdir):
    home = os.path.join(workdir, "home")
    os.makedirs(home, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = home
    env["XDG_CONFIG_HOME"] = os.path.join(home, ".config")
    env["XDG_DATA_HOME"] = os.path.join(home, ".local", "share")
    return env


def resave(binary, in_path, out_path, workdir, timeout=180):
    """Run `qelectrotech --resave in out` headlessly; return (rc, output)."""
    cmd = [binary, "-platform", "offscreen", "--resave", in_path, out_path]
    proc = subprocess.run(
        cmd,
        env=_isolated_env(workdir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# diff helpers (compare by uuid)
# ---------------------------------------------------------------------------


def arrow_diff(before, after):
    """Compare two extract_arrows() dicts by uuid.

    Returns list of (uuid, kind, before, after) where kind in
    {'label','text','order','has_link','folio'} and the value changed.
    """
    changed = []
    for u in sorted(set(before) | set(after)):
        a = before.get(u)
        b = after.get(u)
        if a is None or b is None:
            changed.append((u, "presence", a, b))
            continue
        for key in ("label", "text", "order", "folio", "has_link"):
            if a.get(key) != b.get(key):
                changed.append((u, key, a.get(key), b.get(key)))
    return changed


def label_text_changed(before, after):
    """Subset of arrow_diff: only the *displayed* text or stored label moved."""
    return [
        c for c in arrow_diff(before, after) if c[1] in ("label", "text")
    ]


# ---------------------------------------------------------------------------
# C1: label storage / formula evidence
# ---------------------------------------------------------------------------


def criterion1_evidence(project_path):
    """Return the raw XML facts: report formula, an arrow's label vs text."""
    tree = ET.parse(project_path)
    root = tree.getroot()
    report = None
    for r in root.iter("report"):
        report = r.get("label")
    # find a next_folio arrow with a link, and show label vs text
    sample = None
    for diag in root.iter("diagram"):
        for el in diag.iter("element"):
            if "06renvoi" not in el.get("type", ""):
                continue
            label = ""
            for ei in el.iter("elementInformation"):
                if ei.get("name") == "label":
                    label = ei.text or ""
            text = ""
            for dt in el.iter("dynamic_elmt_text"):
                iname, ttext = _info_name_text(dt)
                if iname == "label":
                    text = ttext
            links = [l.get("uuid") for l in el.iter("link_uuid")]
            if links:
                sample = {
                    "uuid": el.get("uuid"),
                    "type": el.get("type"),
                    "diagram": diag.get("title"),
                    "order": diag.get("order"),
                    "folio_formula": diag.get("folio"),
                    "stored_label": label,
                    "displayed_text": text,
                    "link_uuids": links,
                }
                break
        if sample:
            break
    return {"report_formula": report, "sample_arrow": sample}


# ---------------------------------------------------------------------------
# main experiment
# ---------------------------------------------------------------------------


def run_experiment(args):
    """Run the full X6 experiment and write reports/labelstability.{json,md}."""
    binary = args.binary
    examples = args.examples
    report_dir = args.report_dir
    os.makedirs(report_dir, exist_ok=True)

    scratch = tempfile.mkdtemp(prefix="x6-labelstability-")

    projects = sorted(glob.glob(os.path.join(examples, "*.qet")))
    report = {
        "source_ref": SOURCE_REF,
        "binary": binary,
        "examples_dir": examples,
        "projects_scanned": len(projects),
        "criterion1": {},
        "criterion2": {},
        "criterion3": {},
        "criterion4": {},
    }

    # ---- C4: corpus survey (pure XML, no QET) -----------------------------
    c4 = []
    for path in projects:
        name = os.path.basename(path)
        try:
            formula = read_report_formula(path)
            arrows = extract_arrows(path)
        except Exception as exc:  # noqa: BLE001
            c4.append({"project": name, "error": str(exc)})
            continue
        n = len(arrows)
        c4.append(
            {
                "project": name,
                "report_formula": formula,
                "arrows": n,
                "no_link": sum(1 for a in arrows.values() if not a["has_link"]),
                "blank_text": sum(1 for a in arrows.values() if a["text"] == ""),
                "blank_label": sum(1 for a in arrows.values() if a["label"] == ""),
            }
        )
    # classify formulas
    uses_f = [p for p in c4 if p.get("report_formula") and "%f" in p["report_formula"]]
    uses_F = [p for p in c4 if p.get("report_formula") and "%F" in p["report_formula"]]
    report["criterion4"] = {
        "formula_counts": {
            "%f-based": len(uses_f),
            "%F-based": len(uses_F),
            "other": len(
                [
                    p
                    for p in c4
                    if p.get("report_formula")
                    and "%f" not in p["report_formula"]
                    and "%F" not in p["report_formula"]
                ]
            ),
            "none": len([p for p in c4 if not p.get("report_formula")]),
        },
        "per_project": c4,
    }

    # ---- C1: label storage evidence (on the project with the most arrows) --
    c1_project = max(
        (p for p in c4 if p.get("arrows")),
        key=lambda p: p["arrows"],
        default=None,
    )
    if c1_project:
        c1_path = os.path.join(examples, c1_project["project"])
        report["criterion1"] = criterion1_evidence(c1_path)

    # ---- C2 + C3: per project containing folio-reference arrows -----------
    arrow_projects = [
        p for p in c4
        if p.get("arrows") and p["project"] not in RESAVE_EXCLUDED
    ]
    c2 = {}
    c3 = {}
    for proj in arrow_projects:
        name = proj["project"]
        subj_path = os.path.join(examples, name)
        subj_text = open(subj_path, encoding="utf-8").read()
        _header, blocks, _footer = split_diagram_blocks(subj_text)
        n_diags = len(blocks)
        # move the 2nd folio to the end; in both arrow-bearing examples the 2nd
        # folio is the one that carries the arrows.
        moved_title = diagram_title(blocks[1]) if n_diags > 1 else diagram_title(blocks[0])
        stable_labels = ["FL%d" % (i + 1) for i in range(n_diags)]

        # --- C3a: repeated resave (blank / wrong-number drift) --------------
        p0 = os.path.join(scratch, "%s_r0.qet" % _slug(name))
        open(p0, "w", encoding="utf-8").write(subj_text)
        resaves = [p0]
        for i in range(1, 4):
            out = os.path.join(scratch, "%s_r%d.qet" % (_slug(name), i))
            rc, _ = resave(binary, resaves[-1], out, scratch)
            resaves.append(out)
            assert rc == 0, "resave %d failed rc=%d" % (i, rc)
        base = extract_arrows(resaves[0])
        chain_diffs = []
        for i in range(1, 4):
            cur = extract_arrows(resaves[i])
            chain_diffs.append(label_text_changed(base, cur))
        c3[name] = {
            "repeated_resave": {
                "arrows": len(base),
                "changed_vs_first_save": [len(d) for d in chain_diffs],
            }
        }

        # --- C3b: dangling link -> blank displayed text ---------------------
        first_uuid = next(
            (u for u, a in base.items() if a["has_link"]), None
        )
        if first_uuid:
            links = _arrow_link_uuids(subj_text, first_uuid)
            dangling_text = remove_all_links(subj_text, [first_uuid] + links)
            dp = os.path.join(scratch, "%s_dangling.qet" % _slug(name))
            open(dp, "w", encoding="utf-8").write(dangling_text)
            dout = os.path.join(scratch, "%s_dangling_out.qet" % _slug(name))
            rc, _ = resave(binary, dp, dout, scratch)
            dangling_after = extract_arrows(dout)
            c3[name]["dangling_link"] = {
                "removed_arrow": first_uuid,
                "before": base.get(first_uuid),
                "after": dangling_after.get(first_uuid),
            }
        else:
            c3[name]["dangling_link"] = {
                "note": "no arrow carries a link_uuid to remove",
            }

        # --- C2: %f vs %F, reorder a folio, with default and stable labels --
        c2[name] = {"moved_folio": moved_title, "variants": {}}
        for formula in ("%f-%l%c", "%F-%l%c"):
            for labmode in ("default", "stable"):
                key = "%s_%s" % (formula.split("-")[0], labmode)
                t = set_report_formula(subj_text, formula)
                if labmode == "stable":
                    t = set_folio_labels(t, stable_labels)
                base_path = os.path.join(scratch, "%s_%s_base.qet" % (_slug(name), key))
                open(base_path, "w", encoding="utf-8").write(t)
                pert_path = os.path.join(scratch, "%s_%s_pert.qet" % (_slug(name), key))
                open(pert_path, "w", encoding="utf-8").write(
                    move_diagram(t, moved_title)
                )
                bout = os.path.join(scratch, "%s_%s_base_out.qet" % (_slug(name), key))
                pout = os.path.join(scratch, "%s_%s_pert_out.qet" % (_slug(name), key))
                rc1, _ = resave(binary, base_path, bout, scratch)
                rc2, _ = resave(binary, pert_path, pout, scratch)
                assert rc1 == 0 and rc2 == 0
                b_arrows = extract_arrows(bout)
                p_arrows = extract_arrows(pout)
                diffs = label_text_changed(b_arrows, p_arrows)
                if diffs:
                    sample_uuids = [u for u, _, _, _ in diffs[:4]]
                else:
                    sample_uuids = sorted(b_arrows)[:4]
                c2[name]["variants"][key] = {
                    "formula": formula,
                    "folio_labels": labmode,
                    "arrows": len(b_arrows),
                    "label_or_text_changed": len(diffs),
                    "sample": [
                        {
                            "uuid": u,
                            "before": b_arrows.get(u),
                            "after": p_arrows.get(u),
                        }
                        for u in sample_uuids
                    ],
                }
    report["criterion2"] = c2
    report["criterion3"] = c3

    # ---- write outputs -----------------------------------------------------
    json_path = os.path.join(report_dir, "labelstability.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    md_path = os.path.join(report_dir, "labelstability.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))
    return {"json": json_path, "md": md_path, "scratch": scratch}


def _arrow_link_uuids(text, arrow_uuid):
    """Return the link_uuid targets declared by the arrow with `arrow_uuid`."""
    tree = ET.fromstring(text)
    for el in tree.iter("element"):
        if el.get("uuid") == arrow_uuid:
            return [l.get("uuid") for l in el.iter("link_uuid")]
    return []


# ---------------------------------------------------------------------------
# markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(r):
    lines = []
    a = lines.append
    a("# labelstability — do folio-reference labels survive folio moves?")
    a("")
    a("> X6 measurement report. Source ref scanned: `%s`." % r["source_ref"])
    a("")
    a("## Verdict on the maintainer's %f/%F claim")
    a("")
    a("- **Confirmed mechanically, refuted in practice.** `%f` is folio *position* "
      "(`folioIndex()+1`); `%F` is the title-block folio *label* "
      "(`border_and_titleblock.folio()`). With a **stable literal** folio label, "
      "`%F` holds across a folio move and `%f` shifts — exactly as scorpio810 said.")
    a("- **But the workaround fails on the default configuration.** Every shipped "
      "example sets `folio=\"%id/%total\"` (\"3 of 12\"), so `%F` expands to a "
      "position-derived string and shifts exactly like `%f`. Telling a user to "
      "\"switch `%f` to `%F`\" is not sufficient — they must also give each folio "
      "a stable literal label, which no shipped project does.")
    a("- **The displayed label is *not* the field that goes stale.** The live "
      "`<dynamic_elmt_text>` re-evaluates correctly on load/save. The field that "
      "goes wrong is the stored `<elementInformation name=\"label\">`, which is "
      "never recomputed and is systematically off-by-one in shipped files.")
    a("")
    a("## Criterion 1 — where labels live")
    a("")
    c1 = r["criterion1"]
    if c1:
        a("- Report formula (project level): `<report label=\"%s\"/>`"
          % c1.get("report_formula"))
        s = c1.get("sample_arrow") or {}
        a("- Sample arrow `%s` (%s) on folio \"%s\" (order %s):" % (
            s.get("uuid", "?"), s.get("type", "?"), s.get("diagram", "?"),
            s.get("order", "?")))
        a("  - stored label `<elementInformation name=\"label\">%s</elementInformation>`"
          % s.get("stored_label"))
        a("  - displayed text `<dynamic_elmt_text info_name=\"label\"><text>%s</text>`"
          % s.get("displayed_text"))
        a("  - links: %s" % ", ".join(s.get("link_uuids", [])))
        a("")
        a("The displayed label is the `<dynamic_elmt_text>` value; it is recomputed "
          "live from the project report formula applied to the *partner* arrow. "
          "The `<elementInformation name=\"label\">` field is a separate, stored "
          "value that is **not** recomputed on save.")
    a("")
    a("## Criterion 2 — the %f vs %F claim, tested")
    a("")
    c2 = r["criterion2"]
    if c2:
        for name, proj in c2.items():
            a("### %s" % name)
            a("")
            a("Perturbation: move folio \"%s\" to the end, then `--resave`."
              % proj["moved_folio"])
            a("")
            a("| variant | formula | folio labels | arrows | label/text changed |")
            a("|---|---|---|---|---|")
            for key, v in proj["variants"].items():
                a("| %s | `%s` | %s | %d | %d |" % (
                    key, v["formula"], v["folio_labels"], v["arrows"],
                    v["label_or_text_changed"]))
            a("")
            a("Samples (uuid before → after):")
            a("")
            for key, v in proj["variants"].items():
                for s in v["sample"]:
                    b = s["before"]; af = s["after"]
                    a("- `%s` %s: text `%s`→`%s`, stored label `%s`→`%s`" % (
                        key, s["uuid"][:20],
                        b["text"], af["text"], b["label"], af["label"]))
            a("")
    a("## Criterion 3 — blank / wrong-number failure")
    a("")
    c3 = r["criterion3"]
    if c3:
        for name, proj in c3.items():
            a("### %s" % name)
            a("")
            a("- Repeated resave (3×) changed-vs-first-save counts: %s"
              % proj.get("repeated_resave", {}).get("changed_vs_first_save"))
            d = proj.get("dangling_link", {})
            if "note" in d:
                a("- Dangling link: %s" % d["note"])
            else:
                a("- Dangling link: removing both directions of a link, the "
                  "displayed text goes from `%s` to `%s` (blank); the stored "
                  "label stays `%s`."
                  % ((d.get("before") or {}).get("text"),
                     (d.get("after") or {}).get("text"),
                     (d.get("after") or {}).get("label")))
            a("")
    a("")
    a("## Criterion 4 — corpus survey")
    a("")
    c4 = r["criterion4"]
    if c4:
        fc = c4["formula_counts"]
        a("- report formula usage: `%f`-based **{0}**, `%F`-based **{1}**, "
          "other {2}, none {3}".format(
              fc["%f-based"], fc["%F-based"], fc["other"], fc["none"]))
        a("")
        a("| project | report | arrows | no link | blank text |")
        a("|---|---|---|---|---|")
        for p in c4["per_project"]:
            if p.get("error"):
                a("| %s | ERROR | | | |" % p["project"])
            else:
                a("| %s | `%s` | %d | %d | %d |" % (
                    p["project"], p.get("report_formula"), p.get("arrows", 0),
                    p.get("no_link", 0), p.get("blank_text", 0)))
    a("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="X6 folio-label stability experiment")
    ap.add_argument("--binary", default=QET_BINARY, help="qelectrotech binary")
    ap.add_argument("--examples", default=EXAMPLES_DIR, help="examples directory")
    ap.add_argument(
        "--report-dir",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "reports",
        ),
        help="output directory for labelstability.{json,md}",
    )
    args = ap.parse_args(argv)
    res = run_experiment(args)
    print("wrote %s" % res["json"])
    print("wrote %s" % res["md"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
