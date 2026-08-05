#!/usr/bin/env python3
"""Extract element names from a QET elements/ tree and match each one to an
IEC 81346-2 class code, using the keyword rules in keywords.json.

Longest-phrase-first matching: a rule list sorted by phrase length descending
means a specific multi-word phrase ("circuit breaker") always wins over a
shorter, more ambiguous one ("switch") that might otherwise also appear in
the same name. No match is left as UNMATCHED rather than guessed.

Usage:
    python3 classify.py <elements_dir> [--out report.csv]
"""
import argparse
import csv
import json
from collections import Counter
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def normalize(s: str) -> str:
    # Hyphens/underscores are word separators in element names ("circuit-breaker",
    # "din-rail"), not meaningful punctuation -- without this, a rule phrase
    # written with a space never matches the hyphenated form actually in use.
    s = s.replace("-", " ").replace("_", " ")
    return strip_accents(s).lower()


def load_rules(keywords_path: Path):
    data = json.loads(keywords_path.read_text(encoding="utf-8"))
    rules = [(normalize(r["phrase"]), r["code"]) for r in data["rules"]]
    # Longest phrase first: specific multi-word matches win over generic ones.
    rules.sort(key=lambda r: len(r[0]), reverse=True)
    return rules


def load_class_names(letters_path: Path):
    data = json.loads(letters_path.read_text(encoding="utf-8"))
    return {c["code"]: c["official_class_name"] for c in data["classes"]}


def extract_name(elmt_path: Path):
    """Return (name, source) where source is 'en', 'fr', or 'filename'."""
    try:
        root = ET.parse(elmt_path).getroot()
    except ET.ParseError:
        return elmt_path.stem.replace("_", " "), "filename"

    names = root.find("names")
    if names is not None:
        en = names.find("name[@lang='en']")
        if en is not None and en.text and en.text.strip():
            return en.text.strip(), "en"
        fr = names.find("name[@lang='fr']")
        if fr is not None and fr.text and fr.text.strip():
            return fr.text.strip(), "fr"

    return elmt_path.stem.replace("_", " "), "filename"


def match(text: str, rules):
    norm = normalize(text)
    for phrase, code in rules:
        if phrase in norm:
            return code, phrase
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("elements_dir", type=Path, help="Root dir to scan (e.g. 10_electric/)")
    ap.add_argument("--out", type=Path, default=Path("report.csv"))
    ap.add_argument(
        "--tools-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Directory containing letters.json/keywords.json",
    )
    args = ap.parse_args()

    rules = load_rules(args.tools_dir / "keywords.json")
    class_names = load_class_names(args.tools_dir / "letters.json")

    elmt_files = sorted(args.elements_dir.rglob("*.elmt"))
    if not elmt_files:
        print(f"No .elmt files found under {args.elements_dir}", file=sys.stderr)
        sys.exit(1)

    rows = []
    counts = {}
    name_source_counts = {"en": 0, "fr": 0, "filename": 0}
    unmatched_names = []

    for f in elmt_files:
        name, source = extract_name(f)
        name_source_counts[source] += 1
        category = str(f.parent.relative_to(args.elements_dir))

        code, phrase = match(name, rules)
        match_basis = "name" if code else ""

        if code is None:
            # Fallback: many manufacturer catalog parts (Siemens "6ES7...")
            # have no descriptive word in their own name at all, but sit in
            # a folder whose name says exactly what they are ("01_PLC_
            # controllers"). Same rules, applied to the category path
            # instead -- weaker evidence than a direct name match, so it's
            # recorded separately in the report rather than silently merged.
            code, phrase = match(category, rules)
            if code:
                match_basis = "folder"

        rows.append(
            {
                "file": str(f.relative_to(args.elements_dir)),
                "category": category,
                "name": name,
                "name_source": source,
                "matched_code": code or "",
                "matched_class": class_names.get(code, "") if code else "",
                "matched_phrase": phrase or "",
                "match_basis": match_basis,
            }
        )
        counts[code] = counts.get(code, 0) + 1
        if code is None:
            unmatched_names.append(name)

    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "file",
                "category",
                "name",
                "name_source",
                "matched_code",
                "matched_class",
                "matched_phrase",
                "match_basis",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    total = len(elmt_files)
    matched = total - counts.get(None, 0)
    basis_counts = Counter(r["match_basis"] for r in rows if r["match_basis"])
    print(f"Total elements scanned: {total}")
    print(f"Matched: {matched} ({matched / total * 100:.1f}%)")
    print(f"  from element name:   {basis_counts.get('name', 0)}")
    print(f"  from category folder: {basis_counts.get('folder', 0)} (weaker evidence)")
    print(f"Unmatched: {counts.get(None, 0)} ({counts.get(None, 0) / total * 100:.1f}%)")
    print()
    print("Name source coverage:")
    for src in ("en", "fr", "filename"):
        n = name_source_counts[src]
        print(f"  {src:>9}: {n} ({n / total * 100:.1f}%)")
    print()
    print("Matches by class:")
    for code in sorted(counts.keys(), key=lambda c: (c is None, c)):
        if code is None:
            continue
        print(f"  {code}  {class_names.get(code, '?'):<28} {counts[code]}")
    print()
    print(f"Full report written to {args.out}")


if __name__ == "__main__":
    main()
