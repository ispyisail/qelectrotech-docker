"""
Build the W4 stage-1 corpus: every open, unassigned QET bugtracker issue,
scraped read-only and cached, with a per-bug record and a repro_class guess.

Run:  python3 tools/bugtracker/build_corpus.py [--refresh]

Outputs reports/bugtracker.json (and, via report.py, reports/bugtracker.md).
auto_repro is filled in afterwards by repro.py, which needs the project
attachments downloaded on demand -- this script only records their URLs.

STAGE 1 ONLY: no ranking, no code_paths, no likely_stale, no effort_hint.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from classify import classify_bug
from fetch import FetchCache
from parse import OPEN_STATUS_IDS, ParseError, parse_bug_page, parse_list_page

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
OUT_JSON = REPORTS_DIR / "bugtracker.json"

LIST_URL = "https://qelectrotech.org/bugtracker/view_all_bug_page.php"
BUG_URL = "https://qelectrotech.org/bugtracker/view.php?id={id}"

# The default anonymous filter hides only "closed" (hide_status=90); the list
# therefore contains every non-closed issue. We filter locally to open (status
# 10-50) + unassigned (no handler link) because the tracker's own
# "hide_status=80" filter parameter is accepted but not applied (verified
# 2026-08-16: POSTing hide_status[]=80 still returns resolved issues).
LIST_PER_PAGE = 50


def fetch_list_rows(fc: FetchCache) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        url = LIST_URL if page == 1 else f"{LIST_URL}?page_number={page}"
        html = fc.get(url).decode("utf-8", "replace")
        page_rows = parse_list_page(html)
        if not page_rows:
            raise ParseError(f"list page {page}: zero rows parsed")
        rows.extend(page_rows)
        if len(page_rows) < LIST_PER_PAGE:
            break
        page += 1
        if page > 50:  # safety valve; 244 issues is 5 pages
            raise ParseError("list pagination exceeded 50 pages -- unexpected")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch pages, ignore cache")
    args = ap.parse_args()

    fc = FetchCache(refresh=args.refresh)

    rows = fetch_list_rows(fc)
    total_listed = len(rows)

    open_unassigned = [
        r for r in rows if r["status_id"] in OPEN_STATUS_IDS and not r["has_handler"]
    ]
    open_unassigned.sort(key=lambda r: r["id"])

    print(f"list: {total_listed} non-closed issues; "
          f"{len(open_unassigned)} open+unassigned")

    bugs = []
    errors = []
    for i, row in enumerate(open_unassigned, 1):
        bid = row["id"]
        html = fc.get(BUG_URL.format(id=bid)).decode("utf-8", "replace")
        try:
            rec = parse_bug_page(html, bid)
        except ParseError as e:
            errors.append(str(e))
            print(f"  !! bug {bid}: {e}", file=sys.stderr)
            continue
        # List-page-only fields the detail page does not carry.
        rec["repro_class"] = classify_bug(rec)
        rec["bugnotes_count"] = row["bugnotes_count"]
        rec["attachment_count"] = row["attachment_count"]
        bugs.append(rec)
        print(f"  [{i}/{len(open_unassigned)}] bug {bid}: "
              f"{rec['repro_class']:<9} {rec['summary'][:60]}")

    if errors:
        print(f"\n{len(errors)} bug page(s) failed to parse (see above).", file=sys.stderr)

    from collections import Counter
    dist = Counter(b["repro_class"] for b in bugs)

    out = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "https://qelectrotech.org/bugtracker/",
        "scope": "open + unassigned (stage 1: inventory only, no ranking)",
        "list_total_non_closed": total_listed,
        "open_unassigned_count": len(bugs),
        "repro_class_distribution": dict(sorted(dist.items())),
        "parse_errors": errors,
        "bugs": bugs,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT_JSON} ({len(bugs)} bug records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
