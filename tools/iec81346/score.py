#!/usr/bin/env python3
"""
Score the category classifier against qet_labels.xml, which is the
project's own hand-curated designation data and therefore ground truth.

Every category qet_labels.xml gives a prefix to (directly, or by the
documented inherit-from-parent rule) is a labelled example. For each one
we ask what classify_category.py concludes independently, and compare.

When the two disagree the curated entry is right and the rules are wrong.
Never "fix" a disagreement by editing the expected value.

    python3 tools/iec81346/score.py \\
        --labels elements-10-electric/10_electric/qet_labels.xml
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_category import classify_categories  # noqa: E402


def curated_prefixes(labels_path: Path):
    """category path -> prefix, honouring the file's documented rule that a
    category without a <prefix> of its own inherits its nearest ancestor's."""
    out = {}

    def walk(elem, path, inherited):
        name = elem.get("name")
        here = path + [name] if name else path
        own = elem.find("prefix")
        prefix = own.text.strip() if own is not None and own.text else inherited
        if name and prefix:
            out["/".join(here)] = prefix
        for child in elem.findall("category"):
            walk(child, here, prefix)

    for cat in ET.parse(labels_path).getroot().findall("category"):
        walk(cat, [], None)
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--report", default=Path("tools/iec81346/report.csv"),
                    type=Path)
    ap.add_argument("--keywords", default=Path("tools/iec81346/keywords.json"),
                    type=Path)
    ap.add_argument("--elements-dir",
                    default=Path("elements-10-electric/10_electric"), type=Path)
    ap.add_argument("--show", choices=("wrong", "all", "none"), default="wrong")
    args = ap.parse_args()

    truth = curated_prefixes(args.labels)
    predicted = classify_categories(args.report, args.keywords,
                                    args.elements_dir)

    agree, wrong, missing = [], [], []
    for category, expected in sorted(truth.items()):
        got = predicted.get(category)
        if got is None:
            missing.append((category, expected))
        elif got[0] == expected:
            agree.append((category, expected))
        else:
            wrong.append((category, expected, got))

    total = len(truth)
    print(f"Ground truth: {total} categories with a curated prefix")
    print(f"  agree:   {len(agree):>3}  ({100 * len(agree) / total:.0f}%)")
    print(f"  WRONG:   {len(wrong):>3}")
    print(f"  no call: {len(missing):>3}")
    print()

    if args.show != "none" and wrong:
        print("=== disagreements (curated -> predicted, via basis: evidence) ===")
        for category, expected, got in wrong:
            print(f"  {expected:>3} -> {got[0]:<3} [{got[1]}: {got[2]}]  {category}")
        print()
    if args.show == "all" and missing:
        print("=== no call ===")
        for category, expected in missing:
            print(f"  {expected:>3} -> --   {category}")

    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
