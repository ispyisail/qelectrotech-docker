#!/usr/bin/env python3
"""
Aggregate classify.py's per-element report up to per-category
designation-letter decisions, and (unless --dry-run) write the
attribute into each qualifying category's existing qet_directory file
in a qelectrotech-elements checkout.

A category gets a letter if at least --min-voters elements were
classified by the name/folder/qet_directory tiers (deliberately not
folder_majority, which is itself already an inference from those
tiers -- counting it here would be circular), with more than
--min-agreement of them agreeing on the same class. Every qualifying
category is labeled with a "confidence" tier (high: >=3 voters and
>=0.8 agreement, the original bar, matching classify.py's own
apply_folder_majority_vote() thresholds; low: anything weaker that
still clears --min-voters/--min-agreement) so a wider, noisier sweep
never gets silently blended into the original well-evidenced set --
both the decision CSV and the qet_directory-writing pass keep the two
distinguishable.

A single voter always trivially "agrees" 100% with itself, which is
real evidence (an actual keyword match on an actual element name) but
the weakest kind -- one misclassified element with no siblings to
outvote it. A 2-way tie is not evidence at all, just whichever code
Counter happened to see first -- --min-agreement must be > 0.5 (not
>=) to exclude it; the CLI enforces this.

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

# Folders whose content is diagram notation/annotation, not devices at all --
# no IEC 81346-2 class is correct here, at any confidence level. Found via
# the --min-voters 1 sweep: both elements in 100_folio_referencing are
# cross-page continuation arrows ("Multi wire cable next folio horizontal"),
# which matched "wire" and voted W (guiding object) unanimously -- 2/2
# agreement, so raising the voter/agreement bar alone would not exclude it.
NOT_A_DEVICE_CATEGORY_PREFIXES = (
    "10_allpole/100_folio_referencing",
)

HIGH_CONFIDENCE_MIN_VOTERS = 3
HIGH_CONFIDENCE_MIN_AGREEMENT = 0.8

DIRECT_EVIDENCE_BASES = ("name", "folder", "qet_directory")

ROOT_TAG_RE = re.compile(r"<qet-directory(?P<attrs>[^>]*)>")


def aggregate(report_path: Path, min_voters: int, min_agreement: float):
    by_category = defaultdict(list)
    with report_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_category[row["category"]].append(row)

    decisions = {}
    for category, rows in sorted(by_category.items()):
        if category.startswith(HETEROGENEOUS_FOLDER_PREFIXES):
            continue
        if category.startswith(NOT_A_DEVICE_CATEGORY_PREFIXES):
            continue
        voters = [
            r for r in rows
            if r["matched_code"] and r["match_basis"] in DIRECT_EVIDENCE_BASES
        ]
        if len(voters) < min_voters:
            continue
        counts = Counter(r["matched_code"] for r in voters)
        winner, count = counts.most_common(1)[0]
        agreement = count / len(voters)
        if agreement <= min_agreement:
            continue
        winner_class = next(
            r["matched_class"] for r in voters if r["matched_code"] == winner
        )
        confidence = (
            "high"
            if len(voters) >= HIGH_CONFIDENCE_MIN_VOTERS
            and agreement >= HIGH_CONFIDENCE_MIN_AGREEMENT
            else "low"
        )
        decisions[category] = {
            "letter": winner,
            "class": winner_class,
            "voters": len(voters),
            "agreement": agreement,
            "total_elements": len(rows),
            "confidence": confidence,
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
    ap.add_argument("--min-voters", type=int, default=HIGH_CONFIDENCE_MIN_VOTERS)
    ap.add_argument("--min-agreement", type=float, default=HIGH_CONFIDENCE_MIN_AGREEMENT - 0.001,
                     help="Strict lower bound (agreement must be > this, not >=)")
    args = ap.parse_args()

    if args.min_agreement <= 0.5:
        ap.error("--min-agreement must be > 0.5 -- at or below that is a tie, not evidence")

    decisions = aggregate(args.report, args.min_voters, args.min_agreement)

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
            "confidence": d["confidence"],
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
    confidence_dist = Counter(r["confidence"] for r in decisions.values())
    print(f"Categories qualifying: {len(decisions)} "
          f"(high confidence: {confidence_dist['high']}, low: {confidence_dist['low']})",
          file=sys.stderr)
    print(f"  written:              {written}", file=sys.stderr)
    print(f"  skipped (no qet_directory yet): {skipped_no_dir}", file=sys.stderr)
    print(f"  skipped (already set correctly): {skipped_already_set}", file=sys.stderr)
    print(f"  conflicts (existing letter differs): {len(conflicts)}", file=sys.stderr)
    for cat, cur, new in conflicts:
        print(f"    {cat}: existing={cur} new={new}", file=sys.stderr)
    print("Letter distribution:", dict(sorted(letter_dist.items())), file=sys.stderr)


if __name__ == "__main__":
    main()
