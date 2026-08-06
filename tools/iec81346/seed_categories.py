#!/usr/bin/env python3
"""
Aggregate classify.py's per-element report up to per-category
designation-letter decisions, and (unless --dry-run) write the
attribute into each qualifying category's existing qet_directory file
in a qelectrotech-elements checkout.

Only categories with strong, direct evidence get a letter: at least
MIN_VOTERS elements classified by the name/folder/qet_directory tiers
(deliberately not folder_majority, which is itself already an
inference from those tiers -- counting it here would be circular),
with at least AGREEMENT_THRESHOLD of them agreeing on the same class.
Mirrors classify.py's own apply_folder_majority_vote() thresholds
(min_siblings=3, threshold=0.8) for consistency with the reasoning
already validated there.

Categories that qualify but have no qet_directory file yet are left
alone rather than inventing one with an empty <names> block -- the
existing ElementsLocation::designationLetter() ancestor walk in QET
means a category can still inherit a letter from a parent category
that does have one, so this is a gap, not a loss.

Known-heterogeneous folders are excluded, same list as classify.py.
"""
import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HETEROGENEOUS_FOLDER_PREFIXES = (
    "98_graphics/99_assembly_plan",
)

MIN_VOTERS = 3
AGREEMENT_THRESHOLD = 0.8

DIRECT_EVIDENCE_BASES = ("name", "folder", "qet_directory")

ROOT_TAG_RE = re.compile(r"<qet-directory(?P<attrs>[^>]*)>")


def aggregate(report_path: Path):
    by_category = defaultdict(list)
    with report_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_category[row["category"]].append(row)

    decisions = {}
    for category, rows in sorted(by_category.items()):
        if category.startswith(HETEROGENEOUS_FOLDER_PREFIXES):
            continue
        voters = [
            r for r in rows
            if r["matched_code"] and r["match_basis"] in DIRECT_EVIDENCE_BASES
        ]
        if len(voters) < MIN_VOTERS:
            continue
        counts = Counter(r["matched_code"] for r in voters)
        winner, count = counts.most_common(1)[0]
        agreement = count / len(voters)
        if agreement < AGREEMENT_THRESHOLD:
            continue
        winner_class = next(
            r["matched_class"] for r in voters if r["matched_code"] == winner
        )
        decisions[category] = {
            "letter": winner,
            "class": winner_class,
            "voters": len(voters),
            "agreement": agreement,
            "total_elements": len(rows),
        }
    return decisions


def existing_letter(text: str):
    m = ROOT_TAG_RE.search(text)
    if not m:
        return None
    attrs = m.group("attrs")
    m2 = re.search(r'designation-letter="([^"]*)"', attrs)
    return m2.group(1) if m2 else None


def set_letter(text: str, letter: str) -> str:
    def repl(m):
        attrs = m.group("attrs")
        attrs = re.sub(r'\s*designation-letter="[^"]*"', "", attrs)
        return f'<qet-directory{attrs} designation-letter="{letter}">'

    return ROOT_TAG_RE.sub(repl, text, count=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", default="tools/iec81346/report.csv", type=Path)
    ap.add_argument(
        "--elements-dir",
        required=True,
        type=Path,
        help="Path to 10_electric inside a qelectrotech-elements checkout",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-csv", type=Path, default=None,
                     help="Write the per-category decision table here")
    args = ap.parse_args()

    decisions = aggregate(args.report)

    written, skipped_no_dir, skipped_already_set, conflicts = 0, 0, 0, []
    rows_out = []

    for category, d in decisions.items():
        qet_dir_file = args.elements_dir / category / "qet_directory"
        status = ""
        if not qet_dir_file.exists():
            skipped_no_dir += 1
            status = "no_qet_directory"
        else:
            text = qet_dir_file.read_text(encoding="utf-8")
            current = existing_letter(text)
            if current == d["letter"]:
                skipped_already_set += 1
                status = "already_set"
            elif current and current != d["letter"]:
                conflicts.append((category, current, d["letter"]))
                status = f"CONFLICT_existing={current}"
            else:
                status = "written"
                written += 1
                if not args.dry_run:
                    qet_dir_file.write_text(
                        set_letter(text, d["letter"]), encoding="utf-8"
                    )

        rows_out.append({
            "category": category,
            "letter": d["letter"],
            "class": d["class"],
            "voters": d["voters"],
            "agreement": f"{d['agreement']:.2f}",
            "total_elements": d["total_elements"],
            "status": status,
        })

    if args.out_csv:
        with args.out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            w.writerows(rows_out)

    letter_dist = Counter(r["letter"] for r in decisions.values())
    print(f"Categories qualifying: {len(decisions)}", file=sys.stderr)
    print(f"  written:              {written}", file=sys.stderr)
    print(f"  skipped (no qet_directory yet): {skipped_no_dir}", file=sys.stderr)
    print(f"  skipped (already set correctly): {skipped_already_set}", file=sys.stderr)
    print(f"  conflicts (existing letter differs): {len(conflicts)}", file=sys.stderr)
    for cat, cur, new in conflicts:
        print(f"    {cat}: existing={cur} new={new}", file=sys.stderr)
    print("Letter distribution:", dict(sorted(letter_dist.items())), file=sys.stderr)


if __name__ == "__main__":
    main()
