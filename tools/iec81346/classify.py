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
import re
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
    # Multi-word phrases first, character length only as a tiebreak within
    # the same word count: sorting on raw length alone let "terminal" (8
    # chars, one word) outrank "sensor" (6 chars, one word) in "Magnetic
    # sensor 3 terminals" -- a longer single word isn't automatically a
    # more specific signal than a shorter one, only a longer *phrase* is.
    rules.sort(key=lambda r: (r[0].count(" "), len(r[0])), reverse=True)
    # Word-boundary regex, not plain substring: "led" must not match inside
    # "ledere" (Danish for "conductors") or "self" inside "self-contained".
    # Found by inspection when a Danish qet_directory translation, of all
    # things, silently mis-tagged ~700 unrelated elements -- see git log.
    #
    # A strict \bphrase\b on both sides over-corrects, though: it also
    # stops "controller" matching "controllers", which is how most of these
    # folder names are actually pluralised (English and French both mostly
    # add a bare "s") -- a first attempt at this fix dropped the "folder"
    # tier from 1956 to 888 matches by breaking exactly that. \bphrases?\b
    # keeps the leading boundary (still blocks "led" starting mid-word) and
    # allows one trailing "s" before requiring the boundary there too.
    return [(re.compile(r"\b" + re.escape(phrase) + r"s?\b"), code, phrase) for phrase, code in rules]


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
    for regex, code, phrase in rules:
        if regex.search(norm):
            return code, phrase
    return None, None


_qet_directory_cache = {}


def qet_directory_text(folder: Path):
    """All translated names (every language present, joined) from a single
    folder's own qet_directory file. Cached per folder since many elements
    share the same folder. A folder's slug is sometimes just a manufacturer
    model code ("6ES7-13") in every language that bothers to translate it at
    all -- but occasionally one language (not necessarily English) has a
    genuinely descriptive name where the others just repeat the code, so all
    present languages are checked rather than only "en".
    """
    key = str(folder)
    if key in _qet_directory_cache:
        return _qet_directory_cache[key]

    qd = folder / "qet_directory"
    text = ""
    if qd.is_file():
        try:
            root = ET.parse(qd).getroot()
            names = root.find("names")
            if names is not None:
                text = " ".join(
                    (n.text or "") for n in names.findall("name") if n.text
                )
        except ET.ParseError:
            pass

    _qet_directory_cache[key] = text
    return text


# Folder trees where a leaf folder groups elements by USE CASE (generic
# panel-layout/assembly-drawing icons for whatever device happens to be
# on a schematic) rather than by DEVICE TYPE, so no folder-derived signal
# from anywhere in this tree should be trusted -- not the slug, not
# qet_directory, not a sibling majority vote. Confirmed twice by
# inspection: a 4/4 "unanimous" majority vote in one such folder (four
# name-matched fuses/arresters, coincidentally the entire seed sample)
# got applied to a PLC, a transformer and a drive sitting in the same
# folder; separately, 98_graphics/99_assembly_plan's own qet_directory
# translates to "Armoire" (cabinet), which -- via ancestor-walking --
# mis-tagged a Cognex machine-vision camera as a covering/cabinet object
# purely because it happens to sit somewhere under that tree.
HETEROGENEOUS_FOLDER_PREFIXES = (
    "98_graphics/99_assembly_plan",
)


def qet_directory_text_with_ancestors(elements_dir: Path, category: str):
    """qet_directory text for the leaf category folder plus every ancestor
    up to elements_dir, joined -- so a leaf folder named after a bare model
    code ("6es7-13") still benefits from a more descriptive ancestor
    ("01_PLC_controllers", "Siemens") if the leaf's own qet_directory has
    nothing better than the same code repeated in every language.
    """
    parts = []
    folder = elements_dir / category
    # Walk up to (but not including) elements_dir itself.
    while folder != elements_dir and folder != folder.parent:
        parts.append(qet_directory_text(folder))
        folder = folder.parent
    return " ".join(p for p in parts if p)


def apply_folder_majority_vote(rows, class_names, min_siblings=3, threshold=0.8):
    """Third, weakest fallback: for elements still unmatched after both name
    and folder-keyword matching, look at what their leaf-folder siblings
    already got classified as (by the stronger name/folder-keyword methods
    only -- a majority vote can't feed on its own guesses). If one class
    code accounts for at least `threshold` of those already-classified
    siblings, and there are at least `min_siblings` of them to vote from,
    the remaining unmatched siblings inherit it. A folder that genuinely
    mixes device types won't clear the threshold and is correctly left
    alone -- this is a statistical inference, not a text-pattern match, so
    it's recorded as its own basis rather than folded into "folder".
    """
    by_category = {}
    for r in rows:
        by_category.setdefault(r["category"], []).append(r)

    promoted = 0
    for category, group in by_category.items():
        if category.startswith(HETEROGENEOUS_FOLDER_PREFIXES):
            continue
        voters = [r for r in group if r["matched_code"] and r["match_basis"] in ("name", "folder", "qet_directory")]
        if len(voters) < min_siblings:
            continue
        vote_counts = Counter(r["matched_code"] for r in voters)
        winner, count = vote_counts.most_common(1)[0]
        if count / len(voters) < threshold:
            continue
        for r in group:
            if not r["matched_code"]:
                r["matched_code"] = winner
                r["matched_class"] = class_names.get(winner, "")
                r["matched_phrase"] = f"({count}/{len(voters)} siblings in this folder)"
                r["match_basis"] = "folder_majority"
                promoted += 1
    return promoted


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
    ap.add_argument(
        "--no-majority-vote",
        action="store_true",
        help="Disable the folder-sibling majority-vote fallback",
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
        trust_folder = not category.startswith(HETEROGENEOUS_FOLDER_PREFIXES)

        if code is None and trust_folder:
            # Fallback: many manufacturer catalog parts (Siemens "6ES7...")
            # have no descriptive word in their own name at all, but sit in
            # a folder whose name says exactly what they are ("01_PLC_
            # controllers"). Same rules, applied to the category path
            # instead -- weaker evidence than a direct name match, so it's
            # recorded separately in the report rather than silently merged.
            code, phrase = match(category, rules)
            if code:
                match_basis = "folder"

        if code is None and trust_folder:
            # Second fallback: the folder's own translated display name(s)
            # (qet_directory), walking up through every ancestor. A leaf
            # folder slug is sometimes a bare model code ("6es7-13") in
            # every language including English, but an ancestor folder
            # ("01_PLC_controllers") or an occasional non-English
            # translation can still carry real signal the slug doesn't.
            qd_text = qet_directory_text_with_ancestors(args.elements_dir, category)
            code, phrase = match(qd_text, rules)
            if code:
                match_basis = "qet_directory"

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

    promoted = 0
    if not args.no_majority_vote:
        promoted = apply_folder_majority_vote(rows, class_names)
        # counts/unmatched_names were built during the first pass; recompute
        # from the (possibly updated) rows so the summary reflects reality.
        counts = Counter(r["matched_code"] or None for r in rows)

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
    print(f"  from element name:            {basis_counts.get('name', 0)}")
    print(f"  from category folder slug:    {basis_counts.get('folder', 0)} (weaker evidence)")
    print(f"  from qet_directory name(s):   {basis_counts.get('qet_directory', 0)} (weaker evidence)")
    print(f"  from folder majority vote:    {basis_counts.get('folder_majority', 0)} (weakest evidence)")
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
