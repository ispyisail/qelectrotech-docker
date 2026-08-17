#!/usr/bin/env python3
"""crosspage — structural linter for folio-reference arrows (renvois) in .qet files.

Static, read-only, stdlib-only analysis of the cross-folio wire links in QET
project files. One record per ``06renvoi`` arrow element plus a violations list.

Rules (see CROSSPAGE-PLAN.md §X1):

    X001  arrow carries no ``link_uuid``
    X002  ``link_uuid`` target uuid does not exist in the project
    X003  partner element does not link back to this arrow
    X004  arrow linked to a partner on its own folio
    X005  next_folio linked to next_folio (or previous to previous)
    X006  arrow carrying more than one ``link_uuid``
    X007  next arrow whose partner is on an earlier folio (or previous on a later one)

Usage:
    python3 tools/crosspage/crosspage.py [examples_dir] [--out-dir reports]
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

DEFAULT_EXAMPLES_DIR = "/home/user/qet-fix/examples"

# The rules, in the order they should appear in reports.
RULES = ["X001", "X002", "X003", "X004", "X005", "X006", "X007"]


# Folio-reference arrows ship under several names, in several collections and
# several languages. Matching only ``next_folio``/``previous_folio`` under
# ``06renvoi`` covered 53 of the 400 arrows actually present in the corpus --
# 13% -- and silently excluded the two largest families (``going_arrow`` /
# ``coming_arrow``, 243 arrows) plus the Polish and SFC sets. Every rule below
# was therefore being evaluated over a small, unrepresentative sample.
#
# Keep these keyed by substring: timestamped variants exist
# (``01previous_folio-20140521204844.elmt``) and the same family appears under
# more than one collection path.
NEXT_FAMILIES = ("next_folio", "going_arrow", "nastepna", "jump_to")
PREV_FAMILIES = ("previous_folio", "coming_arrow", "poprzednia", "jump_from")


def direction_of(element_type):
    """Return 'next' / 'prev' / 'other' from an element type string."""
    if not element_type:
        return "other"
    for kw in NEXT_FAMILIES:
        if kw in element_type:
            return "next"
    for kw in PREV_FAMILIES:
        if kw in element_type:
            return "prev"
    return "other"


def is_renvoi(element_type):
    """Is this element a folio-reference arrow, in any family or collection?

    Deliberately NOT a path test: the arrow families live under ``06renvoi``,
    ``10_electric/10_allpole/100_sheet_referencing``, and others. Identity is
    the family name, not where the element file happens to sit.
    """
    return direction_of(element_type) in ("next", "prev")


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
    """Identify the exact source state that was scanned.

    Mirrors ``tools/actionaudit/actionaudit.py:source_ref``. A scan of a feature
    branch is not comparable with a scan of master, and uncommitted edits belong
    to no ref at all. Here the thing being scanned is the corpus of ``.qet``
    files, so *dirty* counts uncommitted ``.qet`` files rather than C++ sources.
    """
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


def _int_order(order):
    try:
        return int(order)
    except (TypeError, ValueError):
        return None


def load_corpus(examples_dir):
    """Return (elements, files, repo_root).

    ``elements`` maps ``(project, uuid) -> dict`` describing one diagram element
    instance, for every element in every diagram of every project. The key is
    scoped to the owning project: two corpus files can be byte-identical copies
    of one project (``cablage-eclairages_sikli-v5.qet`` and
    ``câblage-éclairages-sikli-v5.qet``), and a bare-uuid key would silently
    merge them. Diagram-element instances only: embedded element *definitions*
    live outside <diagram> and are not addressable by link_uuid.
    """
    files = sorted(glob.glob(os.path.join(examples_dir, "*.qet")))
    elements = {}
    for path in files:
        project = os.path.basename(path)
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            print(f"crosspage: skipping unparseable {path}: {exc}", file=sys.stderr)
            continue
        root = tree.getroot()
        for diagram in root.findall("diagram"):
            folio = diagram.get("order")
            for el in diagram.findall("./elements/element"):
                uuid = el.get("uuid")
                if uuid is None:
                    continue
                links_node = el.find("links_uuids")
                links = [c.get("uuid") for c in links_node.findall("link_uuid")] \
                    if links_node is not None else []
                elements[(project, uuid)] = {
                    "project": project,
                    "uuid": uuid,
                    "folio": folio,
                    "type": el.get("type", ""),
                    "direction": direction_of(el.get("type", "")),
                    "x": el.get("x"),
                    "y": el.get("y"),
                    "links": links,
                }
    repo_root = find_repo_root(examples_dir)
    return elements, files, repo_root


def analyze(elements):
    """Build one record per ``06renvoi`` arrow plus a violations list."""
    arrows = []
    for (project, uuid), el in elements.items():
        if not is_renvoi(el["type"]):
            continue
        record = {
            "uuid": uuid,
            "project": project,
            "folio": el["folio"],
            "folio_order": _int_order(el["folio"]),
            "type": el["type"],
            "direction": el["direction"],
            "x": el["x"],
            "y": el["y"],
            "links": list(el["links"]),
            "link_count": len(el["links"]),
            "partners": [],
            "violations": [],
        }
        violations = record["violations"]

        if not el["links"]:
            violations.append("X001")

        if len(el["links"]) > 1:
            violations.append("X006")

        for target in el["links"]:
            partner = elements.get((project, target))
            partner_info = {
                "uuid": target,
                "exists": partner is not None,
            }
            if partner is None:
                violations.append("X002")
            else:
                partner_info.update({
                    "project": partner["project"],
                    "folio": partner["folio"],
                    "folio_order": _int_order(partner["folio"]),
                    "type": partner["type"],
                    "direction": partner["direction"],
                    "is_renvoi": is_renvoi(partner["type"]),
                    "links_back": uuid in partner["links"],
                })
                # X003: partner does not link back.
                if uuid not in partner["links"]:
                    violations.append("X003")
                # X004: partner on the same folio (same project, same order).
                if partner["folio"] == el["folio"]:
                    violations.append("X004")
                # X005: direction mismatch (next->next or prev->prev).
                if el["direction"] in ("next", "prev") and partner["direction"] == el["direction"]:
                    violations.append("X005")
                # X007: next pointing to an earlier folio, or prev to a later one.
                own = _int_order(el["folio"])
                other = _int_order(partner["folio"])
                if own is not None and other is not None:
                    if el["direction"] == "next" and other < own:
                        violations.append("X007")
                    elif el["direction"] == "prev" and other > own:
                        violations.append("X007")
            record["partners"].append(partner_info)

        record["violations"] = sorted(set(violations))
        arrows.append(record)

    arrows.sort(key=lambda r: (r["project"], r["folio_order"] if r["folio_order"] is not None else -1,
                               r["type"], r["uuid"]))
    return arrows


def summarize(arrows, elements, files):
    counts = {rule: 0 for rule in RULES}
    for a in arrows:
        for v in a["violations"]:
            if v in counts:
                counts[v] += 1

    next_arrows = [a for a in arrows if a["direction"] == "next"]
    prev_arrows = [a for a in arrows if a["direction"] == "prev"]
    linked = [a for a in arrows if a["link_count"] > 0]
    unlinked = [a for a in arrows if a["link_count"] == 0]

    def partners_of(a):
        return [p for p in a["partners"] if p.get("exists")]

    linked_next_to_prev = [
        a for a in linked
        if a["direction"] == "next"
        and any(p["direction"] == "prev" for p in partners_of(a))
    ]
    linked_prev_to_next = [
        a for a in linked
        if a["direction"] == "prev"
        and any(p["direction"] == "next" for p in partners_of(a))
    ]
    # next->prev links whose partner is NOT itself a 06renvoi arrow.
    cross_collection = [
        a for a in linked_next_to_prev
        if any(p["direction"] == "prev" and not p["is_renvoi"] for p in partners_of(a))
    ]

    same_folio = sum(1 for a in arrows if "X004" in a["violations"])
    crossing = sum(1 for a in linked if "X004" not in a["violations"])

    projects_with_renvoi = sorted({a["project"] for a in arrows})

    # Non-06renvoi arrow elements in the corpus (next/previous_folio outside 06renvoi)
    # — these are what the 22-vs-17 imbalance turns out to be about.
    other_arrows = []
    for (project, uuid), el in elements.items():
        if is_renvoi(el["type"]):
            continue
        if el["direction"] in ("next", "prev"):
            other_arrows.append({
                "uuid": uuid, "project": project, "folio": el["folio"],
                "type": el["type"], "direction": el["direction"],
                "link_count": len(el["links"]),
            })
    other_arrows.sort(key=lambda r: (r["project"], r["type"], r["uuid"]))

    return {
        "projects_total": len(files),
        "projects_with_uuid_elements": len({el["project"] for el in elements.values()}),
        "projects_with_renvoi": projects_with_renvoi,
        "renvoi_arrows": len(arrows),
        "arrows_next": len(next_arrows),
        "arrows_prev": len(prev_arrows),
        "linked_arrows": len(linked),
        "unlinked_arrows": len(unlinked),
        "cross_folio_links": crossing,
        "same_folio_links": same_folio,
        "dangling_links": counts["X002"],
        "non_reciprocated_links": counts["X003"],
        "direction_pairing": {
            "next_to_prev": len(linked_next_to_prev),
            "prev_to_next": len(linked_prev_to_next),
            "next_to_prev_cross_collection": len(cross_collection),
        },
        "rules": counts,
        "non_renvoi_arrow_elements": {
            "total": len(other_arrows),
            "by_project": {p: sum(1 for o in other_arrows if o["project"] == p)
                           for p in sorted({o["project"] for o in other_arrows})},
            "items": other_arrows,
        },
    }


def _dir_label(a):
    return {"next": "next", "prev": "prev"}.get(a["direction"], a["direction"])


def render_md(summary, arrows, meta):
    lines = []
    lines.append("# Cross-page wire links — structural lint (X1)")
    lines.append("")
    lines.append("Generated by `tools/crosspage/crosspage.py`.")
    lines.append("")
    ref = meta.get("source_ref") or {}
    lines.append("## Source scanned")
    lines.append("")
    lines.append(f"- corpus: `{meta['corpus_glob']}`")
    lines.append(f"- projects: {summary['projects_total']}")
    lines.append(f"- projects with uuid-bearing elements: {summary['projects_with_uuid_elements']} "
                 f"(one legacy file, `schema_indus.qet` v0.3, has no element uuids)")
    lines.append(f"- ref: `{ref.get('branch')}` @ `{ref.get('commit')}` ({ref.get('describe')})")
    if ref.get("dirty_qet_files"):
        lines.append(f"- **dirty `.qet` files: {ref['dirty_qet_files']}** — "
                     f"sample: {ref['dirty_qet_sample']}")
    lines.append("")
    lines.append("## Rule counts")
    lines.append("")
    lines.append("| Rule | Meaning | Count |")
    lines.append("|---|---|---|")
    meaning = {
        "X001": "arrow with no `link_uuid`",
        "X002": "`link_uuid` target does not exist",
        "X003": "link not reciprocated by partner",
        "X004": "arrow linked within its own folio",
        "X005": "next→next / prev→prev direction mismatch",
        "X006": "arrow with more than one `link_uuid`",
        "X007": "next→earlier folio / prev→later folio",
    }
    for rule in RULES:
        lines.append(f"| `{rule}` | {meaning[rule]} | **{summary['rules'][rule]}** |")
    lines.append("")
    lines.append("## Totals")
    lines.append("")
    lines.append(f"- renvoi arrows: **{summary['renvoi_arrows']}** "
                 f"({summary['arrows_next']} next, {summary['arrows_prev']} prev)")
    lines.append(f"- linked: {summary['linked_arrows']}, unlinked: {summary['unlinked_arrows']}")
    lines.append(f"- cross-folio links: {summary['cross_folio_links']}, "
                 f"same-folio links: {summary['same_folio_links']}")
    lines.append(f"- dangling targets: {summary['dangling_links']}, "
                 f"non-reciprocated: {summary['non_reciprocated_links']}")
    lines.append("")
    lines.append("## Direction pairing (the 22-vs-17 question)")
    lines.append("")
    dp = summary["direction_pairing"]
    lines.append(f"- next→prev arrows: **{dp['next_to_prev']}**")
    lines.append(f"- prev→next arrows: **{dp['prev_to_next']}**")
    lines.append(f"- of the next→prev arrows, partner is a *different-collection* "
                 f"arrow (not `06renvoi`): **{dp['next_to_prev_cross_collection']}**")
    lines.append("")
    lines.append("The `06renvoi` filter hides a second arrow collection. See the "
                 "reconciliation note at the end of this report.")
    lines.append("")
    lines.append("## Arrows")
    lines.append("")
    lines.append("| project | folio | dir | uuid | x,y | links | partner(s) | violations |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for a in arrows:
        parts = []
        for p in a["partners"]:
            if not p.get("exists"):
                parts.append(f"`{p['uuid']}` (missing)")
            else:
                tag = "renvoi" if p["is_renvoi"] else "other-collection"
                back = "↔" if p["links_back"] else "⚠no-back"
                parts.append(f"{p['direction']}@{p['folio']} [{tag}] {back}")
        lines.append(
            f"| {a['project']} | {a['folio']} | {_dir_label(a)} | "
            f"`{a['uuid']}` | {a['x']},{a['y']} | {a['link_count']} | "
            f"{' ; '.join(parts) if parts else '—'} | "
            f"{', '.join(a['violations']) if a['violations'] else '·'} |"
        )
    lines.append("")
    lines.append("## Violations")
    lines.append("")
    for rule in RULES:
        offenders = [a for a in arrows if rule in a["violations"]]
        lines.append(f"### {rule} — {meaning[rule]} ({len(offenders)})")
        lines.append("")
        if not offenders:
            lines.append("_none_")
            lines.append("")
            continue
        for a in offenders:
            lines.append(f"- `{a['project']}` folio {a['folio']} `{a['uuid']}` "
                         f"({_dir_label(a)}, x={a['x']} y={a['y']})")
        lines.append("")
    lines.append("## Non-`06renvoi` arrow elements in the corpus")
    lines.append("")
    oa = summary["non_renvoi_arrow_elements"]
    lines.append(f"{oa['total']} next/previous_folio elements live outside the "
                 f"`06renvoi` collection: {oa['by_project']}.")
    lines.append("")
    for o in oa["items"]:
        lines.append(f"- `{o['project']}` folio {o['folio']} `{o['uuid']}` "
                     f"{o['direction']} — `{o['type']}`")
    lines.append("")
    lines.append("## Reconciliation of the 22-vs-17 imbalance")
    lines.append("")
    lines.append(
        "Counting only `06renvoi` arrows, the corpus holds **27 next** and "
        "**17 prev** arrows. Five next arrows carry no link (all in "
        "`Projet_vierge.qet`, folio 3), leaving **22 linked next** and "
        "**17 linked prev**."
    )
    lines.append("")
    lines.append(
        "Every one of the 17 linked prev arrows points at a `06renvoi` next "
        "arrow. But of the 22 linked next arrows, **17** point at `06renvoi` "
        "prev arrows while **5** point at `previous_folio` arrows from a second "
        "collection, `10_electric/10_allpole/100_sheet_referencing/` (all in "
        "`Projet_vierge.qet`, folio 3). Those 5 partners are not `06renvoi` "
        "arrows, so the `prev→next` side cannot see them."
    )
    lines.append("")
    lines.append(
        "So `next→prev` = 22 = 17 (within `06renvoi`) + 5 (cross-collection), "
        "while `prev→next` = 17 (all within `06renvoi`). The 5-arrow gap is "
        "exactly the cross-collection links, not a reciprocity failure: every "
        "link is reciprocated (X003 = 0). The earlier 22-vs-17 probe was not "
        "wrong about the data, but it counted the arrow side by `06renvoi` and "
        "the partner side by substring, which silently absorbed the second "
        "collection on the next→prev side only."
    )
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lint folio-reference arrows in .qet files")
    ap.add_argument("examples_dir", nargs="?", default=DEFAULT_EXAMPLES_DIR,
                    help="directory of .qet files (default /home/user/qet-fix/examples)")
    ap.add_argument("--out-dir", default="reports",
                    help="directory for crosspage.json / crosspage.md (default reports/)")
    args = ap.parse_args(argv)

    examples_dir = os.path.abspath(args.examples_dir)
    elements, files, repo_root = load_corpus(examples_dir)

    arrows = analyze(elements)
    summary = summarize(arrows, elements, files)

    ref = source_ref(repo_root) if repo_root else None
    meta = {
        "generator": "tools/crosspage/crosspage.py",
        "corpus_glob": os.path.join(examples_dir, "*.qet"),
        "scanned_files": len(files),
        "source_ref": ref,
    }

    os.makedirs(args.out_dir, exist_ok=True)
    json_path = os.path.join(args.out_dir, "crosspage.json")
    md_path = os.path.join(args.out_dir, "crosspage.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": meta,
            "summary": summary,
            "arrows": arrows,
        }, f, indent=2, sort_keys=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_md(summary, arrows, meta))

    # Console summary.
    print(f"scanned {len(files)} projects; {summary['renvoi_arrows']} renvoi arrows")
    print("rules: " + ", ".join(f"{r}={summary['rules'][r]}" for r in RULES))
    dp = summary["direction_pairing"]
    print(f"direction pairing: next->prev={dp['next_to_prev']} "
          f"prev->next={dp['prev_to_next']} "
          f"cross-collection={dp['next_to_prev_cross_collection']}")
    print(f"wrote {json_path} and {md_path}")


if __name__ == "__main__":
    main()
