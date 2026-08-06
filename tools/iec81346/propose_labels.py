#!/usr/bin/env python3
"""
Propose new <prefix> entries for qelectrotech-elements' qet_labels.xml.

Output is a *proposal*: a patched copy of the file plus a review CSV, for
a human to check before it ever becomes a pull request. Nothing here
writes to a collection or invents a new data format -- qet_labels.xml is
the project's existing, sanctioned place for designation prefixes.

Safety rules, in the order they bite:

  * a category that already has its own <prefix> is never touched;
  * a category whose subtree carries any *different* prefix (curated or
    proposed) is skipped, because the curator leaves such containers
    blank on purpose -- 395_electronics_semiconductors holds resistors
    (R), capacitors (C), inductors (L) and diodes (V), so stamping any
    one letter on the parent would silently mislabel the others;
  * a proposal identical to what the category already inherits is
    dropped as redundant;
  * where a parent and its descendants all want the same prefix, only
    the parent is proposed and inheritance covers the rest -- that is how
    the existing file is written (50 entries covering 71 categories).

By default only categories the file *already lists* are patched, so every
change is a one-line insertion and the diff stays reviewable. Categories
that would need a new <category> node are reported but not written; pass
--include-unlisted to see them counted in the CSV.

    python3 tools/iec81346/propose_labels.py \\
        --labels elements-10-electric/10_electric/qet_labels.xml \\
        --only 10_allpole --out /tmp/qet_labels.proposed.xml
"""
import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_category import classify_categories  # noqa: E402

CATEGORY_OPEN = re.compile(r'^(\s*)<category\s+name="([^"]*)"\s*>\s*$')
CATEGORY_ONELINE = re.compile(r'^(\s*)<category\s+name="([^"]*)"\s*>\s*</category>\s*$')
CATEGORY_CLOSE = re.compile(r'^\s*</category>\s*$')


def read_labels(path: Path):
    """(listed, own_prefix, effective_prefix) keyed by category path."""
    listed, own, effective = set(), {}, {}

    def walk(elem, path_parts, inherited):
        name = elem.get("name")
        here = path_parts + [name] if name else path_parts
        key = "/".join(here)
        node_prefix = elem.find("prefix")
        text = (node_prefix.text or "").strip() if node_prefix is not None else ""
        current = text or inherited
        if name:
            listed.add(key)
            if text:
                own[key] = text
            if current:
                effective[key] = current
        for child in elem.findall("category"):
            walk(child, here, current)

    for cat in ET.parse(path).getroot().findall("category"):
        walk(cat, [], None)
    return listed, own, effective


def descendants(category: str, all_paths):
    marker = category + "/"
    return [p for p in all_paths if p.startswith(marker)]


def build_proposals(predicted, listed, own, effective):
    """Apply the safety rules, then collapse to the highest category."""
    universe = set(listed) | set(predicted) | set(effective)
    kept, dropped = {}, []

    for category, (code, basis, evidence) in sorted(predicted.items()):
        if category in own:
            dropped.append((category, code, basis, evidence, "already has its own prefix"))
            continue
        if effective.get(category) == code:
            dropped.append((category, code, basis, evidence, "already inherits this prefix"))
            continue

        conflicting = set()
        for child in descendants(category, universe):
            curated = own.get(child)
            if curated and curated != code:
                conflicting.add(curated)
            guess = predicted.get(child)
            if guess and guess[0] != code:
                conflicting.add(guess[0])
        if conflicting:
            dropped.append((category, code, basis, evidence,
                            "subtree also wants " + "/".join(sorted(conflicting))))
            continue

        kept[category] = (code, basis, evidence)

    # Collapse: if an ancestor is proposed the same prefix, inheritance
    # already covers this one.
    collapsed = {}
    for category, value in kept.items():
        parts = category.split("/")
        redundant = any(
            "/".join(parts[:n]) in kept and kept["/".join(parts[:n])][0] == value[0]
            for n in range(1, len(parts))
        )
        if redundant:
            dropped.append((category, value[0], value[1], value[2],
                            "an ancestor is proposed the same prefix"))
        else:
            collapsed[category] = value
    return collapsed, dropped


def patch_text(labels_path: Path, proposals):
    """Insert <prefix> lines, leaving every other byte of the file alone.

    Line-oriented on purpose: re-serialising the XML would reformat the
    whole document and bury a handful of real additions in thousands of
    whitespace-only diff lines.
    """
    lines = labels_path.read_text(encoding="utf-8").splitlines(keepends=True)
    out, stack, applied = [], [], {}
    in_comment = False

    for line in lines:
        # The file opens with a long comment that *documents the format by
        # example*, complete with <category> and </category> tags. Parsing
        # those as real nodes corrupts the path stack and silently
        # misplaces every insertion after it.
        if in_comment:
            out.append(line)
            if "-->" in line:
                in_comment = False
            continue
        if "<!--" in line and "-->" not in line:
            in_comment = True
            out.append(line)
            continue

        one = CATEGORY_ONELINE.match(line)
        if one:
            indent, name = one.group(1), one.group(2)
            key = "/".join(stack + [name])
            if key in proposals:
                code = proposals[key][0]
                out.append(f'{indent}<category name="{name}">\n')
                out.append(f'{indent}  <prefix>{code}</prefix>\n')
                out.append(f"{indent}</category>\n")
                applied[key] = code
            else:
                out.append(line)
            continue

        opened = CATEGORY_OPEN.match(line)
        if opened:
            stack.append(opened.group(2))
            out.append(line)
            continue

        if CATEGORY_CLOSE.match(line) and stack:
            key = "/".join(stack)
            if key in proposals:
                # After the child categories, as the file's own header
                # comment requires.
                indent = re.match(r"^(\s*)", line).group(1)
                out.append(f'{indent}  <prefix>{proposals[key][0]}</prefix>\n')
                applied[key] = proposals[key][0]
            stack.pop()
            out.append(line)
            continue

        out.append(line)

    return "".join(out), applied


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--report", default=Path("tools/iec81346/report.csv"), type=Path)
    ap.add_argument("--keywords", default=Path("tools/iec81346/keywords.json"), type=Path)
    ap.add_argument("--elements-dir",
                    default=Path("elements-10-electric/10_electric"), type=Path)
    ap.add_argument("--only", default="",
                    help="restrict to categories under this path, for batching")
    ap.add_argument("--out", type=Path, help="write the patched XML here")
    ap.add_argument("--review-csv", type=Path)
    ap.add_argument("--include-unlisted", action="store_true",
                    help="also count categories that would need a new <category> node")
    args = ap.parse_args()

    listed, own, effective = read_labels(args.labels)
    predicted = classify_categories(args.report, args.keywords, args.elements_dir)
    if args.only:
        predicted = {k: v for k, v in predicted.items()
                     if k == args.only or k.startswith(args.only + "/")}

    proposals, dropped = build_proposals(predicted, listed, own, effective)

    writable = {k: v for k, v in proposals.items() if k in listed}
    unlisted = {k: v for k, v in proposals.items() if k not in listed}

    patched, applied = patch_text(args.labels,
                                  proposals if args.include_unlisted else writable)

    print(f"classified in scope:            {len(predicted)}")
    print(f"survive the safety rules:       {len(proposals)}")
    print(f"  writable (already listed):    {len(writable)}   <- applied: {len(applied)}")
    print(f"  need a new <category> node:   {len(unlisted)}   <- not written")
    print(f"dropped by the safety rules:    {len(dropped)}")

    if args.out:
        args.out.write_text(patched, encoding="utf-8")
        print(f"\npatched file -> {args.out}")

    if args.review_csv:
        with args.review_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["category", "proposed_prefix", "basis", "evidence", "status"])
            for k, (code, basis, ev) in sorted(writable.items()):
                w.writerow([k, code, basis, ev, "proposed (written)"])
            for k, (code, basis, ev) in sorted(unlisted.items()):
                w.writerow([k, code, basis, ev, "proposed (needs new node)"])
            for k, code, basis, ev, why in sorted(dropped):
                w.writerow([k, code, basis, ev, f"dropped: {why}"])
        print(f"review CSV   -> {args.review_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
