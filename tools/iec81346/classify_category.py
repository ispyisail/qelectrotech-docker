#!/usr/bin/env python3
"""
Classify a *category* (a folder in the element collection) to a
qet_labels.xml prefix.

Deliberately not the same job as classify.py, which classifies individual
elements. qet_labels.xml assigns prefixes per directory, and the curator
plainly named those directories for what they hold ("11_circuit_breakers",
"41_limit_switches"), so the folder name is the strongest available signal
and is tried first. Element names only break the tie when the folder name
says nothing useful -- which does happen, e.g. "20_current_tansformers"
(sic) matches no rule because of the typo, but the elements inside it are
named "Transformateur de courant" and resolve fine.

Order, strongest evidence first:
  1. the leaf folder's own name
  2. the folder's translated names from its qet_directory
  3. a majority vote of the element names inside it

Exposes classify_categories(); score.py and propose_labels.py both use it
so what is measured is exactly what is proposed.
"""
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

# Folders that mix unrelated device kinds by design, so no single prefix is
# right for them. Kept here rather than in the rules because the problem is
# the folder, not any phrase.
HETEROGENEOUS_FOLDER_PREFIXES = (
    "98_graphics/99_assembly_plan",
)

# Folders holding diagram notation rather than devices: no designation
# letter applies at all, at any confidence.
NOT_A_DEVICE_CATEGORY_PREFIXES = (
    "10_allpole/100_folio_referencing",
)

# Everything directly under this is one manufacturer's whole catalogue.
MANUFACTURER_ROOT = "20_manufacturers_articles"


def is_brand_folder(category: str) -> bool:
    """A manufacturer's own top-level folder (and the tree root above it).

    Two reasons to never assign these a prefix. They are heterogeneous by
    definition -- a manufacturer sells terminals, PLCs, power supplies and
    enclosures alike -- so no single letter is right, and because prefixes
    are inherited, one wrong call there would tag that manufacturer's
    entire catalogue. And brand names really do collide with device
    vocabulary: 'phoenix_contact' as a folder name, and "WAGO Contact" in
    WAGO's own qet_directory, both match 'contact' and would otherwise
    resolve to S.
    """
    parts = category.split("/")
    return parts[0] == MANUFACTURER_ROOT and len(parts) <= 2


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[_\-/]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def folder_words(category: str) -> str:
    """Leaf folder name as searchable words: '11_circuit_breakers' ->
    'circuit breakers'. The numeric ordering prefixes carry no meaning."""
    leaf = category.rsplit("/", 1)[-1]
    leaf = re.sub(r"^\d+[_\-]*", "", leaf)
    return normalize(leaf)


def load_rules(keywords_path: Path):
    data = json.loads(keywords_path.read_text(encoding="utf-8"))
    rules = [(normalize(r["phrase"]), r["code"]) for r in data["rules"]]
    # Multi-word phrases first so the most specific wins; character length
    # only breaks ties within the same word count, because a longer single
    # word is not inherently more specific than a shorter one.
    rules.sort(key=lambda r: (r[0].count(" "), len(r[0])), reverse=True)
    # The leading \b stops 'led' matching inside 'ledere'; the optional
    # trailing '(e)s' allows the plural folder names are mostly written in.
    # Plain 's?' is not enough: these folders are full of '..._switches',
    # '..._breakers', '..._fuses', and 'switch' + 's?' does not match
    # 'switches'.
    return [(re.compile(r"\b" + re.escape(p) + r"(?:e?s)?\b"), code, p)
            for p, code in rules]


def match(text: str, rules):
    """First rule (in priority order) that matches anywhere in text.
    Returns (code, phrase); code is None for a suppression rule, which
    means 'deliberately not a match' and lets the caller fall through."""
    norm = normalize(text)
    for regex, code, phrase in rules:
        if regex.search(norm):
            return code, phrase
    return None, None


def qet_directory_text(elements_dir: Path, category: str) -> str:
    """The folder's own translated display names, all languages joined."""
    path = elements_dir / category / "qet_directory"
    if not path.exists():
        return ""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return ""
    return " ".join(n.text or "" for n in root.iter("name"))


def classify_categories(report_path: Path, keywords_path: Path,
                        elements_dir: Path, min_element_votes: int = 3,
                        element_agreement: float = 0.8,
                        min_voter_share: float = 0.5):
    """category -> (code, basis, evidence) for every category we can call."""
    rules = load_rules(keywords_path)

    elements_by_cat = defaultdict(list)
    with report_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            elements_by_cat[row["category"]].append(row)

    # Enumerate from the filesystem, not from the element report: a folder
    # that holds only sub-folders has no elements of its own and so never
    # appears in the report, but qet_labels.xml very much does give such
    # folders a prefix -- that is how the inherit-from-parent rule earns
    # its keep ("390_sensors_instruments" -> P covers ten sensor
    # sub-folders at once).
    categories = sorted(
        str(p.relative_to(elements_dir))
        for p in elements_dir.rglob("*") if p.is_dir())

    out = {}
    for category in categories:
        if category.startswith(HETEROGENEOUS_FOLDER_PREFIXES) \
                or category.startswith(NOT_A_DEVICE_CATEGORY_PREFIXES) \
                or is_brand_folder(category):
            continue

        code, phrase = match(folder_words(category), rules)
        if code:
            out[category] = (code, "folder", phrase)
            continue

        code, phrase = match(qet_directory_text(elements_dir, category), rules)
        if code:
            out[category] = (code, "qet_directory", phrase)
            continue

        # Last resort: what did the elements themselves look like?
        #
        # Only element *name* matches count. classify.py also derives codes
        # for an element from its folder path and from qet_directory text
        # walked up through every ancestor, and both are actively harmful
        # here: the folder/qet_directory signal is already applied above at
        # the level it belongs to, and the ancestor walk drags a
        # manufacturer's brand name down over its whole subtree. WAGO's
        # top-level qet_directory reads "WAGO Contact", which matched
        # 'contact' and made every DIN rail, digital-input card and energy
        # meter under it look like a switching contact (S).
        population = elements_by_cat[category]
        voters = [r["matched_code"] for r in population
                  if r["matched_code"] and r["match_basis"] == "name"]
        if not population or len(voters) < min_element_votes:
            continue
        # A minority of matching names does not describe a folder, however
        # unanimous that minority is. Siemens' "6es7-13" holds 35 I/O
        # cards, of which exactly 4 mention "wire" -- and only because they
        # are 2-/4-wire analogue inputs, nothing to do with cabling. At
        # half, "91_computer_science" also drops out: 4 of its 9 entries
        # are USB/RJ45 sockets (X), the other 5 are PCs and network
        # stations, so no single letter fits the folder.
        if len(voters) / len(population) < min_voter_share:
            continue
        winner, count = Counter(voters).most_common(1)[0]
        if count / len(voters) >= element_agreement:
            out[category] = (winner, "elements",
                             f"{count}/{len(voters)} named, "
                             f"{len(population)} in folder")
    return out
