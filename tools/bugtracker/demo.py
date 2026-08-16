"""
Criterion 4 demonstration: the scraper fails loudly, it does not silently
record an empty string.

Uses real cached pages and a minimal, deterministic corruption (renaming the
HTML class a parser keys on -- exactly what a MantisBT theme change does) to
show that a missing field raises ParseError instead of producing "".
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from fetch import FetchCache
from parse import ParseError, parse_bug_page, parse_list_page

BUG_339 = "https://qelectrotech.org/bugtracker/view.php?id=339"
LIST_P1 = "https://qelectrotech.org/bugtracker/view_all_bug_page.php"


def run_demo() -> str:
    buf = io.StringIO()

    def emit(*a: object) -> None:
        print(*a, file=buf)

    fc = FetchCache()

    # --- clean bug-page parse -------------------------------------------
    html = fc.get(BUG_339).decode("utf-8", "replace")
    rec = parse_bug_page(html, 339)
    emit("[1] clean parse bug 339 ->", repr(rec["summary"]))

    # --- corrupt: rename the description cell's class -------------------
    corrupt = html.replace('class="bug-description"', 'class="bug-description-REMOVED"')
    try:
        parse_bug_page(corrupt, 339)
        emit("[2] BUG: parse of corrupted page did NOT raise")
    except ParseError as e:
        emit("[2] corrupted bug page raises ->", type(e).__name__ + ":", e)

    # --- clean list-page parse ------------------------------------------
    lhtml = fc.get(LIST_P1).decode("utf-8", "replace")
    rows = parse_list_page(lhtml)
    emit(f"[3] clean list parse -> {len(rows)} rows")

    # --- corrupt: rename the summary column -----------------------------
    corrupt_list = lhtml.replace('class="column-summary"', 'class="column-summary-REMOVED"')
    try:
        parse_list_page(corrupt_list)
        emit("[4] BUG: parse of corrupted list did NOT raise")
    except ParseError as e:
        emit("[4] corrupted list page raises ->", type(e).__name__ + ":", e)

    return buf.getvalue()


if __name__ == "__main__":
    sys.stdout.write(run_demo())
